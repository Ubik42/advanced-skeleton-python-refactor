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
    BodyFbxArtifact,
    BodyFbxExportSelection,
    audit_body_fbx_export_readiness,
    inspect_body_fbx_bytes,
    plan_body_fbx_export_selection,
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
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_baked_body_export_skeleton(
        self, plan: BodyExportSkeletonBakePlan
    ) -> BodyExportSkeletonBakedSnapshot: ...
    def capture_body_export_dependency_plugs(
        self, body_root: str, export_paths: tuple[str, ...]
    ) -> tuple[str, ...]: ...
    def prepare_fbx_export_runtime(self) -> str: ...
    def export_fbx_selection(
        self, destination: Path, selection: BodyFbxExportSelection
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BodyFbxExportPlan:
    destination: Path
    body: BodySkeletonSnapshot
    bake: BodyExportSkeletonBakePlan
    baked: BodyExportSkeletonBakedSnapshot
    selection: BodyFbxExportSelection
    body_dependency_plugs: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class BodyFbxExportResult:
    plan: BodyFbxExportPlan
    artifact: BodyFbxArtifact
    plugin_version: str


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
    ) -> BodyFbxExportPlan:
        path = Path(destination)
        if not path.is_absolute() or path.suffix.casefold() != ".fbx":
            raise FitSkeletonValidationError("FBX 导出目标必须是绝对 .fbx 路径")
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise FitSkeletonValidationError("FBX 导出目录不存在或是符号链接")
        if path.exists() or path.is_symlink():
            raise FitSkeletonValidationError("FBX 导出目标已存在，拒绝覆盖")

        body = self._host.capture_body_skeleton(body_root_name)
        provenance = oriented_body_provenance(source_container, len(body.joints))
        root_motion = plan_body_root_motion(
            source_root_path=body.root,
            up_axis=self._host.scene_up_axis(),
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
        selection = plan_body_fbx_export_selection(bake)
        baked = self._host.capture_baked_body_export_skeleton(bake)
        dependencies = self._host.capture_body_export_dependency_plugs(
            body.root, selection.node_paths
        )
        issues = audit_body_fbx_export_readiness(bake, baked, dependencies)
        return BodyFbxExportPlan(
            destination=path,
            body=body,
            bake=bake,
            baked=baked,
            selection=selection,
            body_dependency_plugs=dependencies,
            blockers=tuple(
                issue.message + (f"（{issue.subject}）" if issue.subject else "")
                for issue in (*audit_body_provenance(provenance, body.provenance), *issues)
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
                self._host.capture_body_skeleton(kwargs.get("body_root_name", "Root_M"))
                != plan.body
                or self._host.capture_baked_body_export_skeleton(plan.bake) != plan.baked
                or self._host.capture_body_export_dependency_plugs(
                    plan.body.root, plan.selection.node_paths
                ) != plan.body_dependency_plugs
            ):
                raise RuntimeError("FBX 导出执行前场景输入发生变化")
            self._host.export_fbx_selection(temporary, plan.selection)
            temporary_artifact = inspect_body_fbx_bytes(temporary.read_bytes())
            try:
                os.link(temporary, plan.destination)
            except FileExistsError as error:
                raise FitSkeletonValidationError("FBX 导出目标在发布前已出现") from error
            temporary.unlink()
            temporary = None
            artifact = inspect_body_fbx_bytes(plan.destination.read_bytes())
            if artifact != temporary_artifact:
                raise RuntimeError("FBX 发布文件摘要复检失败")
            return BodyFbxExportResult(plan, artifact, plugin_version)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
