from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_skeleton import (
    BodyJointOrientationChange,
    BodyJointState,
    BodySkeletonSnapshot,
    body_orientation_matches,
    plan_body_joint_orientations,
)
from adv_py.core.fit_orientation import FitOrientationSnapshot
from adv_py.core.fit_settings import FitSkeletonSettings

from .fit_symmetry import FitSymmetryPlan, PlanFitSymmetry


class BodyOrientationHost(Protocol):
    def capture_fit_orientation(
        self, container_name: str
    ) -> FitOrientationSnapshot: ...

    def read_fit_skeleton_settings(
        self, container_name: str
    ) -> FitSkeletonSettings: ...

    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def set_body_joint_world_axes(
        self, change: BodyJointOrientationChange
    ) -> None: ...

    def set_body_joint_world_position(
        self, joint: str, position: tuple[float, float, float]
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BodyOrientationPlan:
    symmetry: FitSymmetryPlan
    before: BodySkeletonSnapshot
    changes: tuple[BodyJointOrientationChange, ...]


@dataclass(frozen=True, slots=True)
class BodyOrientationResult:
    plan: BodyOrientationPlan
    verified: BodySkeletonSnapshot


class OrientBodySkeleton:
    """Apply source and mirrored right-handed frames to a built skeleton."""

    def __init__(self, host: BodyOrientationHost) -> None:
        self._host = host
        self._symmetry = PlanFitSymmetry(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyOrientationPlan:
        symmetry = self._symmetry.execute(
            container_name,
            center_tolerance=center_tolerance,
        )
        before = self._host.capture_body_skeleton(root_name)
        changes = plan_body_joint_orientations(symmetry.instances, before)
        return BodyOrientationPlan(symmetry, before, changes)

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyOrientationResult:
        plan = self.plan(
            container_name,
            root_name=root_name,
            center_tolerance=center_tolerance,
        )
        if not plan.changes:
            return BodyOrientationResult(plan, plan.before)

        with self._host.transaction(
            f"更新 {len(plan.changes)} 个 Body joint 朝向"
        ):
            for change in plan.changes:
                self._host.set_body_joint_world_axes(change)
            for state in sorted(
                plan.before.joints,
                key=lambda item: (item.path.count("|"), item.path),
            ):
                self._host.set_body_joint_world_position(
                    state.path,
                    state.world_position,
                )
            verified = self._host.capture_body_skeleton(root_name)
            self._verify(plan, verified)
            current_fit = self._host.capture_fit_orientation(
                plan.symmetry.source.hierarchy.container
            )
            current_settings = self._host.read_fit_skeleton_settings(
                plan.symmetry.source.hierarchy.container
            )
            if current_fit != plan.symmetry.source:
                raise RuntimeError("Body joint 朝向后复检失败：Fit joints 被改写")
            if current_settings != plan.symmetry.settings:
                raise RuntimeError("Body joint 朝向后复检失败：容器设置被改写")
        return BodyOrientationResult(plan, verified)

    @staticmethod
    def _verify(
        plan: BodyOrientationPlan,
        verified: BodySkeletonSnapshot,
    ) -> None:
        before = {state.path: state for state in plan.before.joints}
        after = {state.path: state for state in verified.joints}
        desired = {
            instance.output_path: instance.world_axes
            for instance in plan.symmetry.instances
        }
        if set(before) != set(after) or set(after) != set(desired):
            raise RuntimeError("Body joint 朝向后复检失败：关节集合发生变化")
        for path, state in after.items():
            previous = before[path]
            if not _body_state_structure_matches(previous, state):
                raise RuntimeError(
                    f"Body joint 朝向后复检失败：结构或标签变化：{path}"
                )
            if any(
                abs(current - wanted) > 1e-5
                for current, wanted in zip(
                    state.world_position,
                    previous.world_position,
                )
            ):
                raise RuntimeError(
                    f"Body joint 朝向后复检失败：世界位置变化：{path}"
                )
            if not body_orientation_matches(desired[path], state):
                raise RuntimeError(
                    f"Body joint 朝向后复检失败：世界轴不一致：{path}"
                )


def _body_state_structure_matches(
    previous: BodyJointState,
    current: BodyJointState,
) -> bool:
    return (
        current.name == previous.name
        and current.parent_path == previous.parent_path
        and current.side is previous.side
        and current.label == previous.label
        and current.writable_joint_orient_axes
        == previous.writable_joint_orient_axes
    )
