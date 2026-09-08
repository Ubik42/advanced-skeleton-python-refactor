from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_root_motion import (
    BodyRootMotionBakePlan,
    BodyRootMotionBakedSnapshot,
    BodyRootMotionPlan,
    BodyRootMotionSample,
    BodyRootMotionSnapshot,
    audit_baked_body_root_motion,
    audit_body_root_motion,
    audit_body_root_motion_samples,
    plan_body_root_motion,
    plan_body_root_motion_bake,
)
from adv_py.core.body_skeleton import (
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_settings import FitSkeletonValidationError


class BodyRootMotionHost(Protocol):
    def scene_up_axis(self) -> FitUpAxis: ...
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_body_root_motion(self, plan: BodyRootMotionPlan) -> None: ...
    def capture_body_root_motion(
        self,
        plan: BodyRootMotionPlan,
    ) -> BodyRootMotionSnapshot: ...
    def sample_body_root_motion(
        self,
        plan: BodyRootMotionBakePlan,
    ) -> tuple[BodyRootMotionSample, ...]: ...
    def bake_body_root_motion(
        self,
        plan: BodyRootMotionBakePlan,
        samples: tuple[BodyRootMotionSample, ...],
    ) -> None: ...
    def capture_baked_body_root_motion(
        self,
        plan: BodyRootMotionBakePlan,
    ) -> BodyRootMotionBakedSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyRootMotionBuildPlan:
    body: BodySkeletonSnapshot
    root_motion: BodyRootMotionPlan
    provenance_blockers: tuple[str, ...]
    name_collisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.provenance_blockers and not self.name_collisions

    @property
    def blockers(self) -> tuple[str, ...]:
        values = list(self.provenance_blockers)
        if self.name_collisions:
            values.append(
                "场景中存在 Root Motion 同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyRootMotionBuildResult:
    plan: BodyRootMotionBuildPlan
    verified: BodyRootMotionSnapshot
    body: BodySkeletonSnapshot


@dataclass(frozen=True, slots=True)
class BodyRootMotionBakeBuildPlan:
    body: BodySkeletonSnapshot
    live: BodyRootMotionSnapshot
    bake: BodyRootMotionBakePlan
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class BodyRootMotionBakeResult:
    plan: BodyRootMotionBakeBuildPlan
    samples: tuple[BodyRootMotionSample, ...]
    verified: BodyRootMotionBakedSnapshot
    body: BodySkeletonSnapshot


class BuildBodyRootMotion:
    """Create a Maya-first planar/yaw driver without changing Body hierarchy."""

    def __init__(self, host: BodyRootMotionHost) -> None:
        self._host = host

    def plan(
        self,
        *,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        output_basename: str = "AdvPy_GameRootMotion",
    ) -> BodyRootMotionBuildPlan:
        body = self._host.capture_body_skeleton(body_root_name)
        expected = oriented_body_provenance(source_container, len(body.joints))
        provenance_issues = audit_body_provenance(expected, body.provenance)
        root_motion = plan_body_root_motion(
            source_root_path=body.root,
            up_axis=self._host.scene_up_axis(),
            output_basename=output_basename,
        )
        collisions = tuple(sorted({
            path
            for name in root_motion.node_names
            for path in self._host.find_name_collisions(name)
        }))
        return BodyRootMotionBuildPlan(
            body=body,
            root_motion=root_motion,
            provenance_blockers=tuple(issue.message for issue in provenance_issues),
            name_collisions=collisions,
        )

    def apply(
        self,
        *,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        output_basename: str = "AdvPy_GameRootMotion",
    ) -> BodyRootMotionBuildResult:
        plan = self.plan(
            body_root_name=body_root_name,
            source_container=source_container,
            output_basename=output_basename,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Root Motion 构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        with self._host.transaction("构建游戏导出 Root Motion 驱动"):
            if self._host.capture_body_skeleton(body_root_name) != plan.body:
                raise RuntimeError("Root Motion 执行前 Body 输入发生变化")
            if any(
                self._host.find_name_collisions(name)
                for name in plan.root_motion.node_names
            ):
                raise RuntimeError("Root Motion 执行前名称发生冲突")
            self._host.create_body_root_motion(plan.root_motion)
            verified = self._host.capture_body_root_motion(plan.root_motion)
            issues = audit_body_root_motion(plan.root_motion, verified)
            if issues:
                raise RuntimeError(
                    "Root Motion 创建后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            body = self._host.capture_body_skeleton(body_root_name)
            if body != plan.body:
                raise RuntimeError("Root Motion 创建改变了 Body skeleton")
        return BodyRootMotionBuildResult(plan, verified, body)


class BakeBodyRootMotion:
    """Sample a live root-motion driver and replace constraints with linear keys."""

    def __init__(self, host: BodyRootMotionHost) -> None:
        self._host = host

    def plan(
        self,
        *,
        start_frame: int,
        end_frame: int,
        sample_by: int = 1,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        output_basename: str = "AdvPy_GameRootMotion",
    ) -> BodyRootMotionBakeBuildPlan:
        body = self._host.capture_body_skeleton(body_root_name)
        expected = oriented_body_provenance(source_container, len(body.joints))
        provenance_issues = audit_body_provenance(expected, body.provenance)
        root_motion = plan_body_root_motion(
            source_root_path=body.root,
            up_axis=self._host.scene_up_axis(),
            output_basename=output_basename,
        )
        bake = plan_body_root_motion_bake(
            root_motion,
            start_frame=start_frame,
            end_frame=end_frame,
            sample_by=sample_by,
        )
        live = self._host.capture_body_root_motion(root_motion)
        live_issues = audit_body_root_motion(root_motion, live)
        return BodyRootMotionBakeBuildPlan(
            body=body,
            live=live,
            bake=bake,
            blockers=tuple(
                issue.message for issue in provenance_issues + live_issues
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
        output_basename: str = "AdvPy_GameRootMotion",
    ) -> BodyRootMotionBakeResult:
        plan = self.plan(
            start_frame=start_frame,
            end_frame=end_frame,
            sample_by=sample_by,
            body_root_name=body_root_name,
            source_container=source_container,
            output_basename=output_basename,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Root Motion bake 预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        with self._host.transaction("烘焙游戏导出 Root Motion 动画"):
            if self._host.capture_body_skeleton(body_root_name) != plan.body:
                raise RuntimeError("Root Motion bake 前 Body 输入发生变化")
            if self._host.capture_body_root_motion(plan.bake.root_motion) != plan.live:
                raise RuntimeError("Root Motion bake 前实时驱动发生变化")
            samples = self._host.sample_body_root_motion(plan.bake)
            sample_issues = audit_body_root_motion_samples(plan.bake, samples)
            if sample_issues:
                raise RuntimeError(
                    "Root Motion 采样复检失败："
                    + "；".join(issue.message for issue in sample_issues)
                )
            self._host.bake_body_root_motion(plan.bake, samples)
            verified = self._host.capture_baked_body_root_motion(plan.bake)
            issues = audit_baked_body_root_motion(plan.bake, samples, verified)
            if issues:
                raise RuntimeError(
                    "Root Motion bake 后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            body = self._host.capture_body_skeleton(body_root_name)
            if body != plan.body:
                raise RuntimeError("Root Motion bake 改变了 Body skeleton")
        return BodyRootMotionBakeResult(plan, samples, verified, body)
