from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Protocol

from adv_py.core.body_export_skeleton import (
    BodyExportSkeletonBakePlan,
    BodyExportSkeletonBakedSnapshot,
    plan_body_export_skeleton,
    plan_body_export_skeleton_bake,
)
from adv_py.core.body_fbx_export import (
    BodyFbxAppliedProfile,
    BodyFbxArtifact,
    BodyFbxEncoding,
    BodyFbxExportProfile,
    BodyFbxExportSelection,
    BodyFbxFileVersion,
    BodyFbxLinearUnit,
    BodyFbxNamingProfile,
    audit_body_fbx_profile,
    audit_body_fbx_export_readiness,
    inspect_body_fbx_bytes,
    plan_body_fbx_export_selection,
    redundant_linear_key_frames,
)
from adv_py.core.body_root_motion import plan_body_root_motion
from adv_py.core.body_skeleton import (
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_settings import FitSkeletonValidationError


class BodyFbxExportHost(Protocol):
    def scene_up_axis(self) -> FitUpAxis: ...
    def scene_linear_unit(self) -> BodyFbxLinearUnit: ...
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_baked_body_export_skeleton(
        self, plan: BodyExportSkeletonBakePlan
    ) -> BodyExportSkeletonBakedSnapshot: ...
    def capture_body_export_dependency_plugs(
        self, body_root: str, export_paths: tuple[str, ...]
    ) -> tuple[str, ...]: ...
    def capture_body_fbx_published_collisions(
        self, selection: BodyFbxExportSelection
    ) -> tuple[str, ...]: ...
    def prepare_fbx_export_runtime(self) -> str: ...
    def export_fbx_selection(
        self,
        destination: Path,
        selection: BodyFbxExportSelection,
        profile: BodyFbxExportProfile,
    ) -> BodyFbxAppliedProfile: ...


@dataclass(frozen=True, slots=True)
class BodyFbxExportPlan:
    destination: Path
    body: BodySkeletonSnapshot
    source_linear_unit: BodyFbxLinearUnit
    profile: BodyFbxExportProfile
    bake: BodyExportSkeletonBakePlan
    baked: BodyExportSkeletonBakedSnapshot
    selection: BodyFbxExportSelection
    body_dependency_plugs: tuple[str, ...]
    published_name_collisions: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class BodyFbxExportResult:
    plan: BodyFbxExportPlan
    artifact: BodyFbxArtifact
    plugin_version: str
    applied_profile: BodyFbxAppliedProfile


class ExportBodyFbx:
    """Publish only a fully baked owned export hierarchy to a new FBX file."""

    def __init__(self, host: BodyFbxExportHost) -> None:
        self._host = host

    def plan(
        self,
        destination: str | os.PathLike[str],
        *,
        start_frame: int,
        end_frame: int,
        sample_by: int = 1,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        root_motion_basename: str = "AdvPy_GameRootMotion",
        output_prefix: str = "AdvPy_EXP_",
        published_root_name: str = "RootMotion",
        naming_profile: BodyFbxNamingProfile | None = None,
        profile: BodyFbxExportProfile | None = None,
    ) -> BodyFbxExportPlan:
        path = Path(destination)
        if not path.is_absolute() or path.suffix.casefold() != ".fbx":
            raise FitSkeletonValidationError("FBX 导出目标必须是绝对 .fbx 路径")
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise FitSkeletonValidationError("FBX 导出目录不存在或是符号链接")
        if path.exists() or path.is_symlink():
            raise FitSkeletonValidationError("FBX 导出目标已存在，拒绝覆盖")

        if profile is not None and not isinstance(profile, BodyFbxExportProfile):
            raise FitSkeletonValidationError("FBX 导出 Profile 类型无效")
        if naming_profile is not None and not isinstance(naming_profile,BodyFbxNamingProfile):
            raise FitSkeletonValidationError("FBX 引擎骨名 Profile 类型无效")
        if naming_profile is not None and published_root_name!="RootMotion":
            raise FitSkeletonValidationError("FBX 引擎骨名 Profile 与独立根名称不能同时指定")
        up_axis = self._host.scene_up_axis()
        source_linear_unit = self._host.scene_linear_unit()
        selected_profile = profile or BodyFbxExportProfile(
            file_version=BodyFbxFileVersion.FBX_2020,
            up_axis=up_axis,
            linear_unit=source_linear_unit,
            encoding=BodyFbxEncoding.BINARY,
        )
        body = self._host.capture_body_skeleton(body_root_name)
        provenance = oriented_body_provenance(source_container, len(body.joints))
        root_motion = plan_body_root_motion(
            source_root_path=body.root,
            up_axis=up_axis,
            output_basename=root_motion_basename,
        )
        export = plan_body_export_skeleton(body, root_motion, output_prefix=output_prefix)
        bake = plan_body_export_skeleton_bake(
            export,
            root_motion,
            start_frame=start_frame,
            end_frame=end_frame,
            sample_by=sample_by,
        )
        selection = plan_body_fbx_export_selection(
            bake, published_root_name=naming_profile.root_name if naming_profile else published_root_name,
            published_joint_names=naming_profile.joint_names if naming_profile else (),
        )
        baked = self._host.capture_baked_body_export_skeleton(bake)
        dependencies = self._host.capture_body_export_dependency_plugs(
            body.root, selection.node_paths
        )
        collisions = self._host.capture_body_fbx_published_collisions(selection)
        issues = audit_body_fbx_export_readiness(bake, baked, dependencies)
        return BodyFbxExportPlan(
            destination=path,
            body=body,
            source_linear_unit=source_linear_unit,
            profile=selected_profile,
            bake=bake,
            baked=baked,
            selection=selection,
            body_dependency_plugs=dependencies,
            published_name_collisions=collisions,
            blockers=tuple(
                issue.message + (f"（{issue.subject}）" if issue.subject else "")
                for issue in (*audit_body_provenance(provenance, body.provenance), *issues)
            ) + tuple(
                f"FBX 发布名称路径已存在：{path}" for path in collisions
            ),
        )

    def apply(self, destination, **kwargs) -> BodyFbxExportResult:
        plan = self.plan(destination, **kwargs)
        if not plan.ready:
            raise FitSkeletonValidationError(
                "FBX 导出预检失败，未写入文件：" + "；".join(plan.blockers)
            )
        plugin_version = self._host.prepare_fbx_export_runtime()
        temporary: Path | None = None
        try:
            handle, temporary_name = tempfile.mkstemp(
                prefix=f".{plan.destination.name}.",
                suffix=".tmp.fbx",
                dir=plan.destination.parent,
            )
            os.close(handle)
            temporary = Path(temporary_name)
            temporary.unlink()
            if plan.destination.exists() or plan.destination.is_symlink():
                raise FitSkeletonValidationError("FBX 导出目标在写入前已出现")
            if (
                self._host.scene_up_axis()
                != plan.bake.root_motion.root_motion.up_axis
                or self._host.scene_linear_unit() != plan.source_linear_unit
                or self._host.capture_body_skeleton(kwargs.get("body_root_name", "Root_M"))
                != plan.body
                or self._host.capture_baked_body_export_skeleton(plan.bake) != plan.baked
                or self._host.capture_body_export_dependency_plugs(
                    plan.body.root, plan.selection.node_paths
                ) != plan.body_dependency_plugs
                or self._host.capture_body_fbx_published_collisions(
                    plan.selection
                ) != plan.published_name_collisions
            ):
                raise RuntimeError("FBX 导出执行前场景输入发生变化")
            applied_profile = self._host.export_fbx_selection(
                temporary, plan.selection, plan.profile
            )
            temporary_artifact = inspect_body_fbx_bytes(temporary.read_bytes())
            profile_issues = audit_body_fbx_profile(
                plan.profile,
                plan.source_linear_unit,
                applied_profile,
                temporary_artifact,
            )
            if profile_issues:
                raise RuntimeError(
                    "FBX Profile 应用复检失败：" + "；".join(profile_issues)
                )
            expected_removed = (
                sum(
                    len(redundant_linear_key_frames(channel.keys))
                    for channel in (
                        *plan.baked.root_motion.channels,
                        *(channel for joint in plan.baked.joints for channel in joint.channels),
                    )
                )
                if plan.profile.curve_policy.value == "lossless_linear" else 0
            )
            if applied_profile.removed_linear_keys != expected_removed:
                raise RuntimeError("FBX 发布曲线简化数量与预检快照不一致")
            try:
                os.link(temporary, plan.destination)
            except FileExistsError as error:
                raise FitSkeletonValidationError("FBX 导出目标在发布前已出现") from error
            temporary.unlink()
            temporary = None
            artifact = inspect_body_fbx_bytes(plan.destination.read_bytes())
            if artifact != temporary_artifact:
                raise RuntimeError("FBX 发布文件摘要复检失败")
            return BodyFbxExportResult(
                plan, artifact, plugin_version, applied_profile
            )
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
