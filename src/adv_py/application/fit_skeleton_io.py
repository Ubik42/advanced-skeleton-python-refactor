from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Protocol

from adv_py.core.fit_container import (
    LOCKED_FIT_CHANNELS,
    FitContainerDisplayStyle,
    FitContainerShape,
    FitContainerSpec,
    FitContainerState,
    FitUpAxis,
    audit_fit_container,
)
from adv_py.core.fit_metadata import FitJointFieldEdit
from adv_py.core.fit_orientation import (
    FitOrientationAxisConfiguration,
    FitOrientationSnapshot,
)
from adv_py.core.fit_settings import (
    FitSkeletonField,
    FitSkeletonSetting,
    FitSkeletonSettings,
    FitSkeletonValidationError,
    audit_fit_skeleton_settings,
    default_fit_skeleton_settings,
)
from adv_py.core.fit_skeleton_io import (
    FIT_SKELETON_DOCUMENT_SUFFIX,
    FIT_SKELETON_NONPORTABLE_SETTING_FIELDS,
    FIT_SKELETON_PORTABLE_SETTING_FIELDS,
    FitSkeletonDocument,
    FitSkeletonDocumentMergePlan,
    FitSkeletonJointDocument,
    FitSkeletonSettingChannelState,
    fit_skeleton_document_from_json,
    fit_skeleton_document_from_snapshot,
    fit_skeleton_document_to_json,
    fit_skeleton_documents_match,
    plan_fit_skeleton_document_merge,
)
from adv_py.core.fit_template import FitJointSpec
from adv_py.core.joint_labels import JointLabel


AxisFrame = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]


class FitSkeletonDocumentHost(Protocol):
    def scene_up_axis(self) -> FitUpAxis: ...
    def inspect_fit_container(self, name: str) -> FitContainerState: ...
    def capture_fit_orientation(
        self,
        container_name: str,
    ) -> FitOrientationSnapshot: ...
    def read_fit_skeleton_settings(
        self,
        container_name: str,
    ) -> FitSkeletonSettings: ...
    def read_joint_label(self, joint: str) -> JointLabel | None: ...
    def capture_fit_skeleton_setting_channels(
        self,
        container_name: str,
    ) -> tuple[FitSkeletonSettingChannelState, ...]: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_fit_container(self, spec: FitContainerSpec) -> str: ...
    def add_fit_skeleton_setting(
        self,
        container: str,
        setting: FitSkeletonSetting,
    ) -> None: ...
    def add_fit_orientation_axis_configuration(
        self,
        container: str,
        configuration: FitOrientationAxisConfiguration,
    ) -> None: ...
    def set_fit_skeleton_setting(
        self,
        container: str,
        setting: FitSkeletonSetting,
    ) -> None: ...
    def create_fit_joint(self, parent: str, spec: FitJointSpec) -> str: ...
    def set_joint_label(self, joint: str, label: JointLabel) -> None: ...
    def apply_fit_joint_edit(
        self,
        joint: str,
        edit: FitJointFieldEdit,
    ) -> None: ...
    def set_fit_joint_world_axes(
        self,
        joint: str,
        world_axes: AxisFrame,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class FitSkeletonSceneInspection:
    container: FitContainerState
    orientation: FitOrientationSnapshot
    settings: FitSkeletonSettings
    labels: tuple[tuple[str, JointLabel], ...]


@dataclass(frozen=True, slots=True)
class FitSkeletonExportPlan:
    destination: Path
    inspection: FitSkeletonSceneInspection
    document: FitSkeletonDocument


@dataclass(frozen=True, slots=True)
class FitSkeletonExportResult:
    plan: FitSkeletonExportPlan
    bytes_written: int


@dataclass(frozen=True, slots=True)
class FitSkeletonSettingChange:
    field: FitSkeletonField
    before: object
    after: object


@dataclass(frozen=True, slots=True)
class FitSkeletonImportPlan:
    source: Path
    document: FitSkeletonDocument
    target: FitSkeletonSceneInspection
    setting_channels: tuple[FitSkeletonSettingChannelState, ...]
    setting_changes: tuple[FitSkeletonSettingChange, ...]
    name_collisions: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers

    @property
    def joint_count(self) -> int:
        return len(self.document.joints)

    @property
    def changed_setting_count(self) -> int:
        return len(self.setting_changes)


@dataclass(frozen=True, slots=True)
class FitSkeletonImportResult:
    plan: FitSkeletonImportPlan
    verified: FitSkeletonSceneInspection
    verified_document: FitSkeletonDocument
    joint_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FitSkeletonCreateImportPlan:
    source: Path
    document: FitSkeletonDocument
    container_spec: FitContainerSpec
    settings: FitSkeletonSettings
    name_collisions: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers

    @property
    def joint_count(self) -> int:
        return len(self.document.joints)


@dataclass(frozen=True, slots=True)
class FitSkeletonCreateImportResult:
    plan: FitSkeletonCreateImportPlan
    verified: FitSkeletonSceneInspection
    verified_document: FitSkeletonDocument
    joint_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FitSkeletonMergePlan:
    source: Path
    incoming_document: FitSkeletonDocument
    target: FitSkeletonSceneInspection
    current_document: FitSkeletonDocument
    document_merge: FitSkeletonDocumentMergePlan
    name_collisions: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers and self.document_merge.ready

    @property
    def added_joint_count(self) -> int:
        return self.document_merge.added_joint_count


@dataclass(frozen=True, slots=True)
class FitSkeletonMergeResult:
    plan: FitSkeletonMergePlan
    verified: FitSkeletonSceneInspection
    verified_document: FitSkeletonDocument
    joint_paths: tuple[str, ...]


class ExportFitSkeleton:
    def __init__(self, host: FitSkeletonDocumentHost) -> None:
        self._host = host

    def plan(
        self,
        destination: str | os.PathLike[str],
        container_name: str = "FitSkeleton",
    ) -> FitSkeletonExportPlan:
        path = _fit_document_path(destination)
        if not path.parent.is_dir():
            raise FitSkeletonValidationError(
                "FitSkeleton 导出目录不存在"
            )
        if path.exists():
            raise FitSkeletonValidationError(
                "FitSkeleton 导出目标已存在，拒绝覆盖"
            )
        inspection = _inspect_scene(self._host, container_name)
        if not inspection.orientation.hierarchy.joints:
            raise FitSkeletonValidationError(
                "FitSkeleton 导出需要至少一个关节"
            )
        document = fit_skeleton_document_from_snapshot(
            inspection.orientation,
            inspection.settings,
            inspection.labels,
        )
        return FitSkeletonExportPlan(path, inspection, document)

    def apply(
        self,
        destination: str | os.PathLike[str],
        container_name: str = "FitSkeleton",
    ) -> FitSkeletonExportResult:
        plan = self.plan(destination, container_name)
        text = fit_skeleton_document_to_json(plan.document)
        temporary = None
        try:
            handle, temporary = tempfile.mkstemp(
                prefix=f".{plan.destination.name}.",
                suffix=".tmp",
                dir=plan.destination.parent,
            )
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            written = Path(temporary).read_text(encoding="utf-8")
            if fit_skeleton_document_from_json(written) != plan.document:
                raise RuntimeError(
                    "FitSkeleton 导出临时文件复检失败"
                )
            if plan.destination.exists():
                raise FitSkeletonValidationError(
                    "FitSkeleton 导出目标在写入前已出现"
                )
            os.replace(temporary, plan.destination)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        saved = plan.destination.read_text(encoding="utf-8")
        if fit_skeleton_document_from_json(saved) != plan.document:
            raise RuntimeError("FitSkeleton 导出文件复检失败")
        return FitSkeletonExportResult(
            plan,
            len(saved.encode("utf-8")),
        )


class ImportFitSkeleton:
    def __init__(self, host: FitSkeletonDocumentHost) -> None:
        self._host = host

    def plan(
        self,
        source: str | os.PathLike[str],
        container_name: str = "FitSkeleton",
    ) -> FitSkeletonImportPlan:
        path = _fit_document_path(source)
        if path.is_symlink() or not path.is_file():
            raise FitSkeletonValidationError(
                "FitSkeleton 导入文件不存在或不是普通文件"
            )
        try:
            document = fit_skeleton_document_from_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValueError) as error:
            raise FitSkeletonValidationError(
                f"FitSkeleton 导入文件损坏：{path.name}"
            ) from error

        target = _inspect_scene(self._host, container_name)
        channels = self._host.capture_fit_skeleton_setting_channels(
            target.container.path
        )
        blockers = list(_import_target_blockers(document, target, channels))
        collisions = tuple(
            sorted(
                {
                    path
                    for joint in document.joints
                    for path in self._host.find_name_collisions(joint.name)
                }
            )
        )
        if collisions:
            blockers.append(
                "场景中存在同名节点：" + "、".join(collisions)
            )
        settings = {item.field: item.value for item in document.settings}
        setting_changes = tuple(
            FitSkeletonSettingChange(
                field,
                target.settings.value(field),
                settings[field],
            )
            for field in FIT_SKELETON_PORTABLE_SETTING_FIELDS
            if target.settings.value(field) != settings[field]
        )
        channel_map = {item.field: item for item in channels}
        for change in setting_changes:
            channel = channel_map.get(change.field)
            if channel is None:
                blockers.append(
                    f"FitSkeleton 设置通道缺失：{change.field.value}"
                )
            elif not channel.writable or channel.incoming_sources:
                blockers.append(
                    f"FitSkeleton 设置不可安全写入：{change.field.value}"
                )
        return FitSkeletonImportPlan(
            path,
            document,
            target,
            channels,
            setting_changes,
            collisions,
            tuple(blockers),
        )

    def apply(
        self,
        source: str | os.PathLike[str],
        container_name: str = "FitSkeleton",
    ) -> FitSkeletonImportResult:
        plan = self.plan(source, container_name)
        if not plan.ready:
            raise FitSkeletonValidationError(
                "FitSkeleton 导入预检失败，场景未修改："
                + "；".join(plan.blockers)
            )
        settings = {item.field: item for item in plan.document.settings}
        with self._host.transaction(
            f"导入 {plan.joint_count} 个 FitSkeleton 关节"
        ):
            current = self.plan(plan.source, plan.target.container.path)
            if current != plan:
                raise FitSkeletonValidationError(
                    "FitSkeleton 导入文件或目标场景在执行前发生变化"
                )
            for change in plan.setting_changes:
                self._host.set_fit_skeleton_setting(
                    plan.target.container.path,
                    settings[change.field],
                )

            paths, created_paths = _materialize_fit_joints(
                self._host,
                plan.target.container.path,
                plan.document.joints,
            )

            try:
                current_document = fit_skeleton_document_from_json(
                    plan.source.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, ValueError) as error:
                raise RuntimeError(
                    "FitSkeleton 导入文件在事务中失效"
                ) from error
            if current_document != plan.document:
                raise RuntimeError(
                    "FitSkeleton 导入文件在事务中发生变化"
                )
            verified = _inspect_scene(
                self._host,
                plan.target.container.path,
            )
            verified_document = fit_skeleton_document_from_snapshot(
                verified.orientation,
                verified.settings,
                verified.labels,
            )
            if not fit_skeleton_documents_match(
                verified_document,
                plan.document,
            ):
                raise RuntimeError(
                    "FitSkeleton 导入后语义复检失败"
                )
        return FitSkeletonImportResult(
            plan,
            verified,
            verified_document,
            created_paths,
        )


class CreateAndImportFitSkeleton:
    """Create a new root container and materialize one document atomically."""

    def __init__(self, host: FitSkeletonDocumentHost) -> None:
        self._host = host

    def plan(
        self,
        source: str | os.PathLike[str],
        container_name: str = "FitSkeleton",
        *,
        display_radius: float = 3.0,
    ) -> FitSkeletonCreateImportPlan:
        path = _fit_document_path(source)
        if path.is_symlink() or not path.is_file():
            raise FitSkeletonValidationError(
                "FitSkeleton 新建导入文件不存在或不是普通文件"
            )
        try:
            document = fit_skeleton_document_from_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValueError) as error:
            raise FitSkeletonValidationError(
                f"FitSkeleton 新建导入文件损坏：{path.name}"
            ) from error

        spec = FitContainerSpec(
            name=container_name,
            display_radius=display_radius,
            up_axis=document.up_axis,
        )
        portable = {item.field: item for item in document.settings}
        defaults = default_fit_skeleton_settings(f"|{spec.name}")
        settings = FitSkeletonSettings(
            f"|{spec.name}",
            tuple(
                portable.get(setting.field, setting)
                for setting in defaults.settings
            ),
        )
        names = (spec.name,) + tuple(
            joint.name for joint in document.joints
        )
        collisions = tuple(
            sorted(
                {
                    collision
                    for name in names
                    for collision in self._host.find_name_collisions(name)
                }
            )
        )
        blockers = []
        if self._host.scene_up_axis() is not document.up_axis:
            blockers.append("文档与 Maya 场景 Up Axis 不一致")
        if collisions:
            blockers.append(
                "容器或待创建关节与场景节点重名："
                + "、".join(collisions)
            )
        return FitSkeletonCreateImportPlan(
            path,
            document,
            spec,
            settings,
            collisions,
            tuple(blockers),
        )

    def apply(
        self,
        source: str | os.PathLike[str],
        container_name: str = "FitSkeleton",
        *,
        display_radius: float = 3.0,
    ) -> FitSkeletonCreateImportResult:
        plan = self.plan(
            source,
            container_name,
            display_radius=display_radius,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "FitSkeleton 新建导入预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        with self._host.transaction(
            f"新建并导入 {plan.joint_count} 个 FitSkeleton 关节"
        ):
            current = self.plan(
                plan.source,
                plan.container_spec.name,
                display_radius=plan.container_spec.display_radius,
            )
            if current != plan:
                raise FitSkeletonValidationError(
                    "FitSkeleton 新建导入文件或场景在执行前发生变化"
                )
            container = self._host.create_fit_container(plan.container_spec)
            if container != plan.settings.container:
                raise RuntimeError(
                    "FitSkeleton 新建导入容器路径与计划不一致"
                )
            for setting in plan.settings.settings:
                self._host.add_fit_skeleton_setting(container, setting)
            self._host.add_fit_orientation_axis_configuration(
                container,
                plan.document.axis_configuration,
            )
            _, created_paths = _materialize_fit_joints(
                self._host,
                container,
                plan.document.joints,
            )

            try:
                current_document = fit_skeleton_document_from_json(
                    plan.source.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, ValueError) as error:
                raise RuntimeError(
                    "FitSkeleton 新建导入文件在事务中失效"
                ) from error
            if current_document != plan.document:
                raise RuntimeError(
                    "FitSkeleton 新建导入文件在事务中发生变化"
                )
            verified = _inspect_scene(self._host, container)
            container_issues = audit_fit_container(
                verified.container,
                plan.container_spec,
            )
            if container_issues:
                raise RuntimeError(
                    "FitSkeleton 新建导入容器复检失败："
                    + "；".join(issue.message for issue in container_issues)
                )
            verified_document = fit_skeleton_document_from_snapshot(
                verified.orientation,
                verified.settings,
                verified.labels,
            )
            if not fit_skeleton_documents_match(
                verified_document,
                plan.document,
            ):
                raise RuntimeError(
                    "FitSkeleton 新建导入后语义复检失败"
                )
        return FitSkeletonCreateImportResult(
            plan,
            verified,
            verified_document,
            created_paths,
        )


class MergeFitSkeleton:
    """Add missing document branches while preserving every existing joint."""

    def __init__(self, host: FitSkeletonDocumentHost) -> None:
        self._host = host

    def plan(
        self,
        source: str | os.PathLike[str],
        container_name: str = "FitSkeleton",
    ) -> FitSkeletonMergePlan:
        path = _fit_document_path(source)
        if path.is_symlink() or not path.is_file():
            raise FitSkeletonValidationError(
                "FitSkeleton 合并文件不存在或不是普通文件"
            )
        try:
            incoming = fit_skeleton_document_from_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValueError) as error:
            raise FitSkeletonValidationError(
                f"FitSkeleton 合并文件损坏：{path.name}"
            ) from error

        target = _inspect_scene(self._host, container_name)
        current = fit_skeleton_document_from_snapshot(
            target.orientation,
            target.settings,
            target.labels,
        )
        document_merge = plan_fit_skeleton_document_merge(current, incoming)
        collisions = tuple(
            sorted(
                {
                    collision
                    for name in document_merge.added_joint_names
                    for collision in self._host.find_name_collisions(name)
                }
            )
        )
        blockers = [issue.message for issue in document_merge.issues]
        if collisions:
            blockers.append(
                "待新增关节与场景节点重名：" + "、".join(collisions)
            )
        return FitSkeletonMergePlan(
            path,
            incoming,
            target,
            current,
            document_merge,
            collisions,
            tuple(blockers),
        )

    def apply(
        self,
        source: str | os.PathLike[str],
        container_name: str = "FitSkeleton",
    ) -> FitSkeletonMergeResult:
        plan = self.plan(source, container_name)
        if not plan.ready:
            raise FitSkeletonValidationError(
                "FitSkeleton 合并预检失败，场景未修改："
                + "；".join(plan.blockers)
            )
        if plan.added_joint_count == 0:
            return FitSkeletonMergeResult(
                plan,
                plan.target,
                plan.current_document,
                (),
            )

        expected = plan.document_merge.merged
        if expected is None:
            raise RuntimeError("FitSkeleton 合并计划缺少预期文档")
        incoming = {
            joint.name: joint for joint in plan.incoming_document.joints
        }
        additions = tuple(
            incoming[name]
            for name in plan.document_merge.added_joint_names
        )
        existing_paths = {
            node.short_name: node.path
            for node in plan.target.orientation.hierarchy.joints
        }
        with self._host.transaction(
            f"合并 {plan.added_joint_count} 个 FitSkeleton 关节"
        ):
            current = self.plan(plan.source, plan.target.container.path)
            if current != plan:
                raise FitSkeletonValidationError(
                    "FitSkeleton 合并文件或目标场景在执行前发生变化"
                )
            _, created_paths = _materialize_fit_joints(
                self._host,
                plan.target.container.path,
                additions,
                existing_paths=existing_paths,
            )

            try:
                current_incoming = fit_skeleton_document_from_json(
                    plan.source.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, ValueError) as error:
                raise RuntimeError(
                    "FitSkeleton 合并文件在事务中失效"
                ) from error
            if current_incoming != plan.incoming_document:
                raise RuntimeError(
                    "FitSkeleton 合并文件在事务中发生变化"
                )
            verified = _inspect_scene(
                self._host,
                plan.target.container.path,
            )
            verified_document = fit_skeleton_document_from_snapshot(
                verified.orientation,
                verified.settings,
                verified.labels,
            )
            if not fit_skeleton_documents_match(
                verified_document,
                expected,
            ):
                raise RuntimeError(
                    "FitSkeleton 合并后语义复检失败"
                )
        return FitSkeletonMergeResult(
            plan,
            verified,
            verified_document,
            created_paths,
        )


def _materialize_fit_joints(
    host: FitSkeletonDocumentHost,
    container: str,
    joints: tuple[FitSkeletonJointDocument, ...],
    *,
    existing_paths: dict[str, str] | None = None,
) -> tuple[dict[str, str], tuple[str, ...]]:
    paths = dict(existing_paths or {})
    created_paths = []
    for joint in joints:
        if joint.name in paths:
            raise RuntimeError(
                f"FitSkeleton 物化计划重复创建关节：{joint.name}"
            )
        parent = container
        if joint.parent is not None:
            parent = paths.get(joint.parent, "")
            if not parent:
                raise RuntimeError(
                    f"FitSkeleton 物化计划缺少已创建父级：{joint.name}"
                )
        path = host.create_fit_joint(
            parent,
            FitJointSpec(
                joint.name,
                joint.parent,
                joint.local_position,
                joint.label,
            ),
        )
        host.set_joint_label(path, joint.label)
        for value in joint.metadata:
            host.apply_fit_joint_edit(
                path,
                FitJointFieldEdit(value.field, value.value),
            )
        host.set_fit_joint_world_axes(path, joint.world_axes)
        paths[joint.name] = path
        created_paths.append(path)
    return paths, tuple(created_paths)


def _inspect_scene(
    host: FitSkeletonDocumentHost,
    container_name: str,
) -> FitSkeletonSceneInspection:
    container = host.inspect_fit_container(container_name)
    errors = _container_errors(container)
    if errors:
        raise FitSkeletonValidationError(
            "FitSkeleton 容器不满足保存/加载合同："
            + "；".join(errors)
        )
    orientation = host.capture_fit_orientation(container.path)
    if (
        orientation.hierarchy.container != container.path
        or orientation.up_axis is not host.scene_up_axis()
    ):
        raise FitSkeletonValidationError(
            "FitSkeleton 层级、容器或场景 Up Axis 不一致"
        )
    settings = host.read_fit_skeleton_settings(container.path)
    if settings.container != container.path:
        raise FitSkeletonValidationError(
            "FitSkeleton 设置不属于目标容器"
        )
    issues = audit_fit_skeleton_settings(settings, require_complete=True)
    if issues:
        raise FitSkeletonValidationError(
            "FitSkeleton 设置无效："
            + "；".join(issue.message for issue in issues)
        )
    labels = []
    for node in orientation.hierarchy.joints:
        label = host.read_joint_label(node.path)
        if label is None:
            raise FitSkeletonValidationError(
                f"Fit joint 缺少可移植标签：{node.short_name}"
            )
        labels.append((node.path, label))
    return FitSkeletonSceneInspection(
        container,
        orientation,
        settings,
        tuple(labels),
    )


def _container_errors(state: FitContainerState) -> tuple[str, ...]:
    errors = []
    if state.path != f"|{state.short_name}":
        errors.append("容器必须位于场景根级")
    if state.shape is not FitContainerShape.RING:
        errors.append("容器必须保留本工程圆环形状")
    if state.display_style is not FitContainerDisplayStyle.FIT:
        errors.append("容器必须保留 Fit 显示样式")
    if LOCKED_FIT_CHANNELS - state.locked_channels:
        errors.append("容器平移和旋转通道必须锁定")
    if any(abs(value) > 1e-5 for value in state.local_translation):
        errors.append("容器平移必须为零")
    if any(abs(value) > 1e-5 for value in state.local_rotation):
        errors.append("容器旋转必须为零")
    if any(abs(value - 1.0) > 1e-5 for value in state.local_scale):
        errors.append("容器缩放必须为一")
    return tuple(errors)


def _import_target_blockers(
    document: FitSkeletonDocument,
    target: FitSkeletonSceneInspection,
    channels: tuple[FitSkeletonSettingChannelState, ...],
) -> tuple[str, ...]:
    blockers = []
    if target.orientation.hierarchy.joints:
        blockers.append("目标 FitSkeleton 必须为空")
    if target.orientation.joints or target.orientation.metadata or target.labels:
        blockers.append("空目标包含计划外关节数据")
    if target.orientation.up_axis is not document.up_axis:
        blockers.append("文档与 Maya 场景 Up Axis 不一致")
    if target.orientation.axis_configuration != document.axis_configuration:
        blockers.append("文档与目标 FitSkeleton 轴配置不一致")
    populated = tuple(
        field.value
        for field in FIT_SKELETON_NONPORTABLE_SETTING_FIELDS
        if target.settings.value(field) != ""
    )
    if populated:
        blockers.append(
            "目标包含场景路径或脚本文本：" + "、".join(populated)
        )
    channel_fields = tuple(item.field for item in channels)
    if len(channel_fields) != len(set(channel_fields)):
        blockers.append("FitSkeleton 设置通道快照包含重复字段")
    if set(channel_fields) != target.settings.present_fields:
        blockers.append("FitSkeleton 设置通道快照不完整")
    for channel in channels:
        if target.settings.value(channel.field) != channel.value:
            blockers.append(
                f"FitSkeleton 设置值与通道快照不一致：{channel.field.value}"
            )
    return tuple(blockers)


def _fit_document_path(value: str | os.PathLike[str]) -> Path:
    try:
        path = Path(value).expanduser().resolve()
    except (TypeError, ValueError, OSError) as error:
        raise FitSkeletonValidationError(
            "FitSkeleton 文档路径无效"
        ) from error
    if not path.name.casefold().endswith(
        FIT_SKELETON_DOCUMENT_SUFFIX.casefold()
    ):
        raise FitSkeletonValidationError(
            f"FitSkeleton 文档必须使用 {FIT_SKELETON_DOCUMENT_SUFFIX} 后缀"
        )
    return path
