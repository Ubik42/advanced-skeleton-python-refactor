from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

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
