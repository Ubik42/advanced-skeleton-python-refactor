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
    BodyExportSourceJoint,
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
    body_skeleton_unchanged,
    expected_body_provenance,
)
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_settings import FitSkeletonValidationError


def _capture_export_source_joints(host, root_name: str):
    """Older host doubles retain their Body-only publication behavior."""
    capture = getattr(host, "capture_body_export_source_joints", None)
    return capture(root_name) if capture is not None else None


class BodyExportSkeletonHost(Protocol):
    def scene_up_axis(self) -> FitUpAxis: ...
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_export_source_joints(
        self, root_name: str,
    ) -> tuple[BodyExportSourceJoint, ...]: ...
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
    source_joints: tuple[BodyExportSourceJoint, ...] | None
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
    source_joints: tuple[BodyExportSourceJoint, ...] | None
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
        source_container: str | None = None,
        root_motion_basename: str = "AdvPy_GameRootMotion",
        output_prefix: str = "AdvPy_EXP_",
    ) -> BodyExportSkeletonBuildPlan:
        body = self._host.capture_body_skeleton(body_root_name)
        source_joints = _capture_export_source_joints(self._host, body_root_name)
        expected = expected_body_provenance(body, source_container)
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
            source_joints=source_joints,
        )
        collisions = tuple(sorted({
            path
            for name in export_skeleton.node_names
            for path in self._host.find_name_collisions(name)
        }))
        return BodyExportSkeletonBuildPlan(
            body=body,
            source_joints=source_joints,
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
        source_container: str | None = None,
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
            if not body_skeleton_unchanged(plan.body,
                self._host.capture_body_skeleton(body_root_name)):
                raise RuntimeError("Export Skeleton 执行前 Body 输入发生变化")
            if _capture_export_source_joints(self._host, body_root_name) != plan.source_joints:
                raise RuntimeError("Export Skeleton 执行前物理关节层级发生变化")
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
            if not body_skeleton_unchanged(plan.body, body):
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
        source_container: str | None = None,
        root_motion_basename: str = "AdvPy_GameRootMotion",
        output_prefix: str = "AdvPy_EXP_",
    ) -> BodyExportSkeletonBakeBuildPlan:
        body = self._host.capture_body_skeleton(body_root_name)
        source_joints = _capture_export_source_joints(self._host, body_root_name)
        expected = expected_body_provenance(body, source_container)
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
            source_joints=source_joints,
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
            source_joints=source_joints,
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
        source_container: str | None = None,
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
            if not body_skeleton_unchanged(plan.body,
                self._host.capture_body_skeleton(body_root_name)):
                raise RuntimeError("Export Skeleton bake 前 Body 输入发生变化")
            if _capture_export_source_joints(self._host, body_root_name) != plan.source_joints:
                raise RuntimeError("Export Skeleton bake 前物理关节层级发生变化")
            if (
                self._host.capture_body_root_motion(root_motion)
                != plan.root_motion_snapshot
                or self._host.capture_body_export_skeleton(export)
                != plan.export_snapshot
            ):
                raise RuntimeError("Export Skeleton bake 前实时层级发生变化")
            source_samples = self._host.sample_body_export_skeleton(plan.bake)
            sample_issues = audit_body_export_skeleton_samples(
                plan.bake,
                source_samples,
            )
            if sample_issues:
                raise RuntimeError(
                    "Export Skeleton 采样复检失败："
                    + "；".join(issue.message for issue in sample_issues)
                )
            self._host.bake_body_export_skeleton(plan.bake, source_samples)
            samples = self._host.sample_body_export_skeleton(plan.bake)
            if audit_body_export_skeleton_samples(plan.bake,samples):
                raise RuntimeError('Export Skeleton bake 后样本结构变化')
            if any(before.frame!=after.frame
                    or any(abs(a-b)>1e-5 for a,b in zip(
                        before.root_motion.translation
                        +before.root_motion.rotation,
                        after.root_motion.translation
                        +after.root_motion.rotation))
                    or any(
                    left.output_path!=right.output_path
                    or (left.source_world_matrix is None)
                       != (right.source_world_matrix is None)
                    or (left.source_world_matrix is not None and any(
                        abs(a-b)>1e-5 for a,b in zip(
                            left.source_world_matrix,
                            right.source_world_matrix)))
                    or (left.source_world_matrix is None and any(
                        abs(a-b)>1e-5 for a,b in zip(
                            left.translation+left.rotation+left.scale,
                            right.translation+right.rotation+right.scale)))
                    for left,right in zip(before.joints,after.joints))
                    for before,after in zip(source_samples,samples)):
                raise RuntimeError(
                    'Export Skeleton bake 改变了来源关节世界姿态')
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
            if not body_skeleton_unchanged(plan.body, body):
                raise RuntimeError("Export Skeleton bake 改变了 Body skeleton")
        return BodyExportSkeletonBakeResult(plan, samples, verified, body)
