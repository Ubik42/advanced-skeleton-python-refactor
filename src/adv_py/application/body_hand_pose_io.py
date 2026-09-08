from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Protocol

from adv_py.core.body_hand_controls import (
    BodyHandFkControlPlan,
    BodyHandFkControlSnapshot,
    BodyHandPosePlan,
    BodyHandPoseSnapshot,
    audit_body_hand_fk_controls,
    audit_body_hand_pose_controls,
    plan_body_hand_fk_controls,
    plan_body_hand_pose_controls,
)
from adv_py.core.body_hand_pose_io import (
    BodyHandPoseAccessMode,
    BodyHandPoseChangeSet,
    BodyHandPoseChannelSnapshot,
    BodyHandPoseDocument,
    audit_body_hand_pose_channels,
    body_hand_pose_changes,
    body_hand_pose_document_from_json,
    body_hand_pose_document_from_snapshot,
    body_hand_pose_document_to_json,
)
from adv_py.core.body_skeleton import (
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_settings import FitSkeletonValidationError


class BodyHandPoseDocumentHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_hand_fk_controls(
        self,
        plan: BodyHandFkControlPlan,
    ) -> BodyHandFkControlSnapshot: ...
    def capture_body_hand_pose(
        self,
        plan: BodyHandPosePlan,
    ) -> BodyHandPoseSnapshot: ...
    def capture_body_hand_pose_channels(
        self,
        hand: BodyHandFkControlPlan,
        pose: BodyHandPosePlan,
    ) -> BodyHandPoseChannelSnapshot: ...
    def apply_body_hand_pose_changes(
        self,
        changes: BodyHandPoseChangeSet,
        *,
        keyframe: bool = False,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BodyHandPoseRigInspection:
    body: BodySkeletonSnapshot
    hand: BodyHandFkControlPlan
    pose: BodyHandPosePlan
    hand_snapshot: BodyHandFkControlSnapshot
    pose_snapshot: BodyHandPoseSnapshot
    channels: BodyHandPoseChannelSnapshot


@dataclass(frozen=True, slots=True)
class BodyHandPoseExportPlan:
    destination: Path
    rig: BodyHandPoseRigInspection
    document: BodyHandPoseDocument


@dataclass(frozen=True, slots=True)
class BodyHandPoseExportResult:
    plan: BodyHandPoseExportPlan
    bytes_written: int


@dataclass(frozen=True, slots=True)
class BodyHandPoseImportPlan:
    source: Path
    document: BodyHandPoseDocument
    rig: BodyHandPoseRigInspection
    changes: BodyHandPoseChangeSet
    access_mode: BodyHandPoseAccessMode

    @property
    def changed_channel_count(self) -> int:
        return self.changes.changed_channel_count


@dataclass(frozen=True, slots=True)
class BodyHandPoseImportResult:
    plan: BodyHandPoseImportPlan
    rig: BodyHandPoseRigInspection

    @property
    def changed_channel_count(self) -> int:
        return self.plan.changed_channel_count


class InspectBodyHandPoseRig:
    """Validate the owned Maya Hand rig without requiring a neutral pose."""

    def __init__(self, host: BodyHandPoseDocumentHost) -> None:
        self._host = host

    def execute(
        self,
        *,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        expected_joint_count: int = 70,
        control_radius: float = 0.3,
        access_mode: BodyHandPoseAccessMode = BodyHandPoseAccessMode.READ_ONLY,
    ) -> BodyHandPoseRigInspection:
        body = self._host.capture_body_skeleton(body_root_name)
        provenance_issues = audit_body_provenance(
            oriented_body_provenance(source_container, expected_joint_count),
            body.provenance,
        )
        if provenance_issues:
            raise FitSkeletonValidationError(
                "Hand Pose 需要本工程拥有的完整 70 关节 Body："
                + "；".join(issue.message for issue in provenance_issues)
            )
        namespace = _body_namespace(body)
        hand = plan_body_hand_fk_controls(
            body,
            radius=control_radius,
            namespace=namespace,
        )
        pose = plan_body_hand_pose_controls(hand)
        hand_snapshot = self._host.capture_body_hand_fk_controls(hand)
        hand_issues = audit_body_hand_fk_controls(
            hand,
            hand_snapshot,
            check_initial_pose=False,
        )
        pose_snapshot = self._host.capture_body_hand_pose(pose)
        pose_issues = audit_body_hand_pose_controls(
            pose,
            pose_snapshot,
            check_initial_pose=False,
        )
        channels = self._host.capture_body_hand_pose_channels(hand, pose)
        channel_issues = audit_body_hand_pose_channels(
            hand,
            pose,
            channels,
            access_mode=access_mode,
        )
        issues = hand_issues + pose_issues + channel_issues
        if issues:
            raise FitSkeletonValidationError(
                "Hand Pose 场景结构预检失败，场景未修改："
                + "；".join(
                    issue.message
                    + (f"：{issue.subject}" if issue.subject is not None else "")
                    for issue in issues
                )
            )
        return BodyHandPoseRigInspection(
            body,
            hand,
            pose,
            hand_snapshot,
            pose_snapshot,
            channels,
        )


class ExportBodyHandPose:
    def __init__(self, host: BodyHandPoseDocumentHost) -> None:
        self._inspector = InspectBodyHandPoseRig(host)

    def plan(
        self,
        destination: str | os.PathLike[str],
        **inspection_options,
    ) -> BodyHandPoseExportPlan:
        path = _json_path(destination)
        if not path.parent.is_dir():
            raise FitSkeletonValidationError("Hand Pose 导出目录不存在")
        if path.exists():
            raise FitSkeletonValidationError("Hand Pose 导出目标已存在，拒绝覆盖")
        rig = self._inspector.execute(
            access_mode=BodyHandPoseAccessMode.READ_ONLY,
            **inspection_options,
        )
        document = body_hand_pose_document_from_snapshot(rig.channels)
        return BodyHandPoseExportPlan(path, rig, document)

    def apply(
        self,
        destination: str | os.PathLike[str],
        **inspection_options,
    ) -> BodyHandPoseExportResult:
        plan = self.plan(destination, **inspection_options)
        text = body_hand_pose_document_to_json(plan.document)
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
            if body_hand_pose_document_from_json(written) != plan.document:
                raise RuntimeError("Hand Pose 导出临时文件复检失败")
            if plan.destination.exists():
                raise FitSkeletonValidationError(
                    "Hand Pose 导出目标在写入前已出现"
                )
            os.replace(temporary, plan.destination)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        saved = plan.destination.read_text(encoding="utf-8")
        if body_hand_pose_document_from_json(saved) != plan.document:
            raise RuntimeError("Hand Pose 导出文件复检失败")
        return BodyHandPoseExportResult(plan, len(saved.encode("utf-8")))


class ImportBodyHandPose:
    def __init__(self, host: BodyHandPoseDocumentHost) -> None:
        self._host = host
        self._inspector = InspectBodyHandPoseRig(host)

    def plan(
        self,
        source: str | os.PathLike[str],
        *,
        keyframe: bool = False,
        **inspection_options,
    ) -> BodyHandPoseImportPlan:
        if not isinstance(keyframe, bool):
            raise FitSkeletonValidationError(
                "Hand Pose keyframe 选项必须是布尔值"
            )
        path = _json_path(source)
        if not path.is_file():
            raise FitSkeletonValidationError("Hand Pose 导入文件不存在")
        document = body_hand_pose_document_from_json(
            path.read_text(encoding="utf-8")
        )
        access_mode = (
            BodyHandPoseAccessMode.KEYFRAME_WRITE
            if keyframe
            else BodyHandPoseAccessMode.STATIC_WRITE
        )
        rig = self._inspector.execute(
            access_mode=access_mode,
            **inspection_options,
        )
        changes = body_hand_pose_changes(document, rig.channels)
        return BodyHandPoseImportPlan(
            path,
            document,
            rig,
            changes,
            access_mode,
        )

    def apply(
        self,
        source: str | os.PathLike[str],
        *,
        keyframe: bool = False,
        **inspection_options,
    ) -> BodyHandPoseImportResult:
        plan = self.plan(
            source,
            keyframe=keyframe,
            **inspection_options,
        )
        current_document = body_hand_pose_document_from_json(
            plan.source.read_text(encoding="utf-8")
        )
        if current_document != plan.document:
            raise FitSkeletonValidationError(
                "Hand Pose 导入文件在执行前发生变化"
            )
        current_rig = self._inspector.execute(
            access_mode=plan.access_mode,
            **inspection_options,
        )
        if current_rig != plan.rig:
            raise FitSkeletonValidationError(
                "Hand Pose 导入场景在执行前发生变化"
            )
        if plan.changed_channel_count == 0:
            return BodyHandPoseImportResult(plan, current_rig)

        label = (
            "在当前帧导入双手 Hand Pose"
            if plan.access_mode is BodyHandPoseAccessMode.KEYFRAME_WRITE
            else "导入双手 Hand Pose"
        )
        with self._host.transaction(label):
            transaction_document = body_hand_pose_document_from_json(
                plan.source.read_text(encoding="utf-8")
            )
            if transaction_document != plan.document:
                raise RuntimeError("Hand Pose 事务开始后导入文件发生变化")
            transaction_rig = self._inspector.execute(
                access_mode=plan.access_mode,
                **inspection_options,
            )
            if transaction_rig != plan.rig:
                raise RuntimeError("Hand Pose 事务开始后场景发生变化")
            self._host.apply_body_hand_pose_changes(
                plan.changes,
                keyframe=(
                    plan.access_mode is BodyHandPoseAccessMode.KEYFRAME_WRITE
                ),
            )
            result_rig = self._inspector.execute(
                access_mode=plan.access_mode,
                **inspection_options,
            )
            result_document = body_hand_pose_document_from_snapshot(
                result_rig.channels
            )
            if result_document != plan.document:
                raise RuntimeError("Hand Pose 导入后姿态复检失败")
        return BodyHandPoseImportResult(plan, result_rig)


def _json_path(value: str | os.PathLike[str]) -> Path:
    try:
        path = Path(value).expanduser().resolve()
    except (TypeError, ValueError, OSError) as error:
        raise FitSkeletonValidationError("Hand Pose 文件路径无效") from error
    if path.suffix.casefold() != ".json":
        raise FitSkeletonValidationError("Hand Pose 文件必须使用 .json 扩展名")
    return path


def _body_namespace(body: BodySkeletonSnapshot) -> str | None:
    root_leaf = body.root.rsplit("|", 1)[-1]
    namespace, separator, root_name = root_leaf.rpartition(":")
    if root_name != "Root_M":
        raise FitSkeletonValidationError(
            "Hand Pose Body 根必须使用 Root_M 基名"
        )
    expected = namespace if separator else None
    for joint in body.joints:
        leaf = joint.path.rsplit("|", 1)[-1]
        current, has_namespace, _name = leaf.rpartition(":")
        actual = current if has_namespace else None
        if actual != expected:
            raise FitSkeletonValidationError(
                "Hand Pose Body joints 必须位于同一 Maya namespace"
            )
    return expected
