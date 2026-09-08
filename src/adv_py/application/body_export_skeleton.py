from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_export_skeleton import (
    BodyExportSkeletonBakePlan,
    BodyExportSkeletonBakedSnapshot,
    BodyExportSkeletonPlan,
    BodyExportSkeletonSample,
    BodyExportSkeletonSnapshot,
    audit_baked_body_export_skeleton,
    audit_body_export_skeleton,
    audit_body_export_skeleton_samples,
    plan_body_export_skeleton,
    plan_body_export_skeleton_bake,
)
from adv_py.core.body_root_motion import (
    BodyRootMotionPlan,
    BodyRootMotionSnapshot,
    audit_body_root_motion,
    plan_body_root_motion,
)
from adv_py.core.body_skeleton import (
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_settings import FitSkeletonValidationError


class BodyExportSkeletonHost(Protocol):
    def scene_up_axis(self) -> FitUpAxis: ...
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_root_motion(
        self,
        plan: BodyRootMotionPlan,
    ) -> BodyRootMotionSnapshot: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_body_export_skeleton(self, plan: BodyExportSkeletonPlan) -> None: ...
    def capture_body_export_skeleton(
        self,
        plan: BodyExportSkeletonPlan,
    ) -> BodyExportSkeletonSnapshot: ...
    def sample_body_export_skeleton(
        self,
        plan: BodyExportSkeletonBakePlan,
    ) -> tuple[BodyExportSkeletonSample, ...]: ...
    def bake_body_export_skeleton(
        self,
        plan: BodyExportSkeletonBakePlan,
        samples: tuple[BodyExportSkeletonSample, ...],
    ) -> None: ...
    def capture_baked_body_export_skeleton(
        self,
        plan: BodyExportSkeletonBakePlan,
    ) -> BodyExportSkeletonBakedSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonBuildPlan:
    body: BodySkeletonSnapshot
    root_motion: BodyRootMotionPlan
    root_motion_snapshot: BodyRootMotionSnapshot
    export_skeleton: BodyExportSkeletonPlan
    blockers: tuple[str, ...]
    name_collisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers and not self.name_collisions

    @property
    def problems(self) -> tuple[str, ...]:
        values = list(self.blockers)
        if self.name_collisions:
            values.append(
                "场景中存在 Export Skeleton 同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonBuildResult:
    plan: BodyExportSkeletonBuildPlan
    verified: BodyExportSkeletonSnapshot
    body: BodySkeletonSnapshot


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonBakeBuildPlan:
    body: BodySkeletonSnapshot
    root_motion_snapshot: BodyRootMotionSnapshot
    export_snapshot: BodyExportSkeletonSnapshot
    bake: BodyExportSkeletonBakePlan
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class BodyExportSkeletonBakeResult:
    plan: BodyExportSkeletonBakeBuildPlan
    samples: tuple[BodyExportSkeletonSample, ...]
    verified: BodyExportSkeletonBakedSnapshot
    body: BodySkeletonSnapshot


class BuildBodyExportSkeleton:
    """Build an owned live export hierarchy below a verified root-motion joint."""

    def __init__(self, host: BodyExportSkeletonHost) -> None:
        self._host = host

    def plan(
        self,
        *,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        root_motion_basename: str = "AdvPy_GameRootMotion",
        output_prefix: str = "AdvPy_EXP_",
    ) -> BodyExportSkeletonBuildPlan:
        body = self._host.capture_body_skeleton(body_root_name)
        expected = oriented_body_provenance(source_container, len(body.joints))
        provenance_issues = audit_body_provenance(expected, body.provenance)
        root_motion = plan_body_root_motion(
            source_root_path=body.root,
            up_axis=self._host.scene_up_axis(),
            output_basename=root_motion_basename,
        )
        root_motion_snapshot = self._host.capture_body_root_motion(root_motion)
        root_motion_issues = audit_body_root_motion(
            root_motion,
            root_motion_snapshot,
        )
        export_skeleton = plan_body_export_skeleton(
            body,
            root_motion,
            output_prefix=output_prefix,
        )
        collisions = tuple(sorted({
            path
            for name in export_skeleton.node_names
            for path in self._host.find_name_collisions(name)
        }))
        return BodyExportSkeletonBuildPlan(
            body=body,
            root_motion=root_motion,
            root_motion_snapshot=root_motion_snapshot,
            export_skeleton=export_skeleton,
            blockers=tuple(
                issue.message
                for issue in provenance_issues + root_motion_issues
            ),
            name_collisions=collisions,
        )

    def apply(
        self,
        *,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        root_motion_basename: str = "AdvPy_GameRootMotion",
        output_prefix: str = "AdvPy_EXP_",
    ) -> BodyExportSkeletonBuildResult:
        plan = self.plan(
            body_root_name=body_root_name,
            source_container=source_container,
            root_motion_basename=root_motion_basename,
            output_prefix=output_prefix,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Export Skeleton 构建预检失败，场景未修改："
                + "；".join(plan.problems)
            )

        with self._host.transaction("构建游戏导出 Skeleton"):
            if self._host.capture_body_skeleton(body_root_name) != plan.body:
                raise RuntimeError("Export Skeleton 执行前 Body 输入发生变化")
            if (
                self._host.capture_body_root_motion(plan.root_motion)
                != plan.root_motion_snapshot
            ):
                raise RuntimeError("Export Skeleton 执行前 Root Motion 发生变化")
            if any(
                self._host.find_name_collisions(name)
                for name in plan.export_skeleton.node_names
            ):
                raise RuntimeError("Export Skeleton 执行前名称发生冲突")
            self._host.create_body_export_skeleton(plan.export_skeleton)
            verified = self._host.capture_body_export_skeleton(
                plan.export_skeleton
            )
            issues = audit_body_export_skeleton(
                plan.export_skeleton,
                verified,
            )
            if issues:
                raise RuntimeError(
                    "Export Skeleton 创建后复检失败："
                    + "；".join(
                        issue.message
                        + (f"（{issue.subject}）" if issue.subject else "")
                        for issue in issues
                    )
                )
            body = self._host.capture_body_skeleton(body_root_name)
            if body != plan.body:
                raise RuntimeError("Export Skeleton 创建改变了 Body skeleton")
            if (
                self._host.capture_body_root_motion(plan.root_motion)
                != plan.root_motion_snapshot
            ):
                raise RuntimeError("Export Skeleton 创建改变了 Root Motion")
        return BodyExportSkeletonBuildResult(plan, verified, body)


class BakeBodyExportSkeleton:
    """Bake root motion and all export joints into one independent hierarchy."""

    def __init__(self, host: BodyExportSkeletonHost) -> None:
        self._host = host

    def plan(
        self,
        *,
        start_frame: int,
        end_frame: int,
        sample_by: int = 1,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        root_motion_basename: str = "AdvPy_GameRootMotion",
        output_prefix: str = "AdvPy_EXP_",
    ) -> BodyExportSkeletonBakeBuildPlan:
        body = self._host.capture_body_skeleton(body_root_name)
        expected = oriented_body_provenance(source_container, len(body.joints))
        provenance_issues = audit_body_provenance(expected, body.provenance)
        root_motion = plan_body_root_motion(
            source_root_path=body.root,
            up_axis=self._host.scene_up_axis(),
            output_basename=root_motion_basename,
        )
        root_motion_snapshot = self._host.capture_body_root_motion(root_motion)
        root_motion_issues = audit_body_root_motion(
            root_motion,
            root_motion_snapshot,
        )
        export = plan_body_export_skeleton(
            body,
            root_motion,
            output_prefix=output_prefix,
        )
        export_snapshot = self._host.capture_body_export_skeleton(export)
        export_issues = audit_body_export_skeleton(export, export_snapshot)
        bake = plan_body_export_skeleton_bake(
            export,
            root_motion,
            start_frame=start_frame,
            end_frame=end_frame,
            sample_by=sample_by,
        )
        return BodyExportSkeletonBakeBuildPlan(
            body=body,
            root_motion_snapshot=root_motion_snapshot,
            export_snapshot=export_snapshot,
            bake=bake,
            blockers=tuple(
                issue.message
                for issue in provenance_issues
                + root_motion_issues
                + export_issues
            ),
        )

    def apply(
        self,
        *,
        start_frame: int,
        end_frame: int,
        sample_by: int = 1,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        root_motion_basename: str = "AdvPy_GameRootMotion",
        output_prefix: str = "AdvPy_EXP_",
    ) -> BodyExportSkeletonBakeResult:
        plan = self.plan(
            start_frame=start_frame,
            end_frame=end_frame,
            sample_by=sample_by,
            body_root_name=body_root_name,
            source_container=source_container,
            root_motion_basename=root_motion_basename,
            output_prefix=output_prefix,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Export Skeleton bake 预检失败，场景未修改："
                + "；".join(plan.blockers)
            )
        export = plan.bake.export_skeleton
        root_motion = plan.bake.root_motion.root_motion
        with self._host.transaction("烘焙独立游戏导出 Skeleton"):
            if self._host.capture_body_skeleton(body_root_name) != plan.body:
                raise RuntimeError("Export Skeleton bake 前 Body 输入发生变化")
            if (
                self._host.capture_body_root_motion(root_motion)
                != plan.root_motion_snapshot
                or self._host.capture_body_export_skeleton(export)
                != plan.export_snapshot
            ):
                raise RuntimeError("Export Skeleton bake 前实时层级发生变化")
            samples = self._host.sample_body_export_skeleton(plan.bake)
            sample_issues = audit_body_export_skeleton_samples(
                plan.bake,
                samples,
            )
            if sample_issues:
                raise RuntimeError(
                    "Export Skeleton 采样复检失败："
                    + "；".join(issue.message for issue in sample_issues)
                )
            self._host.bake_body_export_skeleton(plan.bake, samples)
            verified = self._host.capture_baked_body_export_skeleton(plan.bake)
            issues = audit_baked_body_export_skeleton(
                plan.bake,
                samples,
                verified,
            )
            if issues:
                raise RuntimeError(
                    "Export Skeleton bake 后复检失败："
                    + "；".join(
                        issue.message
                        + (f"（{issue.subject}）" if issue.subject else "")
                        for issue in issues
                    )
                )
            body = self._host.capture_body_skeleton(body_root_name)
            if body != plan.body:
                raise RuntimeError("Export Skeleton bake 改变了 Body skeleton")
        return BodyExportSkeletonBakeResult(plan, samples, verified, body)
