from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_hierarchy import audit_fit_hierarchy
from adv_py.core.fit_orientation import (
    FitJointOrientationState,
    FitOrientationChange,
    FitOrientationRequest,
    FitOrientationSnapshot,
    FitOrientationValidationError,
    orientation_matches,
    plan_simple_fit_orientations,
)
from adv_py.core.fit_settings import (
    FitSkeletonSettings,
    audit_fit_skeleton_settings,
)


class FitOrientationHost(Protocol):
    def capture_fit_orientation(
        self, container_name: str
    ) -> FitOrientationSnapshot: ...

    def read_fit_skeleton_settings(
        self, container_name: str
    ) -> FitSkeletonSettings: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def orient_fit_joint(self, change: FitOrientationChange) -> None: ...


@dataclass(frozen=True, slots=True)
class FitOrientationPlan:
    before: FitOrientationSnapshot
    before_settings: FitSkeletonSettings
    changes: tuple[FitOrientationChange, ...]


@dataclass(frozen=True, slots=True)
class FitOrientationResult:
    plan: FitOrientationPlan
    verified: FitOrientationSnapshot


class OrientSimpleFitChain:
    """Aim local X at the sole child while keeping a stable local Y reference."""

    def __init__(self, host: FitOrientationHost) -> None:
        self._host = host

    def plan(
        self,
        request: FitOrientationRequest,
        container_name: str = "FitSkeleton",
    ) -> FitOrientationPlan:
        before = self._host.capture_fit_orientation(container_name)
        settings = self._host.read_fit_skeleton_settings(
            before.hierarchy.container
        )
        setting_issues = audit_fit_skeleton_settings(settings, require_complete=True)
        if setting_issues:
            raise FitOrientationValidationError(
                "FitSkeleton 容器设置无效："
                + "；".join(issue.message for issue in setting_issues)
            )
        changes = plan_simple_fit_orientations(before, request)
        return FitOrientationPlan(before, settings, changes)

    def apply(
        self,
        request: FitOrientationRequest,
        container_name: str = "FitSkeleton",
    ) -> FitOrientationResult:
        plan = self.plan(request, container_name)
        if not plan.changes:
            return FitOrientationResult(plan, plan.before)

        with self._host.transaction(
            f"更新 {len(plan.changes)} 个 Fit joint 朝向"
        ):
            for change in plan.changes:
                self._host.orient_fit_joint(change)
            verified = self._host.capture_fit_orientation(
                plan.before.hierarchy.container
            )
            settings = self._host.read_fit_skeleton_settings(
                plan.before.hierarchy.container
            )
            self._verify(plan, verified, settings)
        return FitOrientationResult(plan, verified)

    @staticmethod
    def _verify(
        plan: FitOrientationPlan,
        verified: FitOrientationSnapshot,
        settings: FitSkeletonSettings,
    ) -> None:
        issues = audit_fit_hierarchy(verified.hierarchy)
        if issues:
            raise RuntimeError(
                "Fit joint 朝向修改后复检失败："
                + "；".join(issue.message for issue in issues)
            )
        if settings != plan.before_settings:
            raise RuntimeError("Fit joint 朝向修改后复检失败：容器设置被改写")

        before_nodes = {node.path: node for node in plan.before.hierarchy.joints}
        after_nodes = {node.path: node for node in verified.hierarchy.joints}
        if set(before_nodes) != set(after_nodes):
            raise RuntimeError("Fit joint 朝向修改后复检失败：节点集合发生变化")
        for path, previous in before_nodes.items():
            current = after_nodes[path]
            if (
                current.short_name != previous.short_name
                or current.dag_parent != previous.dag_parent
                or current.locked_translation_axes
                != previous.locked_translation_axes
                or current.writable_translation_axes
                != previous.writable_translation_axes
            ):
                raise RuntimeError(
                    f"Fit joint 朝向修改后复检失败：{current.short_name} 状态变化"
                )
            if any(
                abs(a - b) > 1e-5
                for a, b in zip(current.world_position, previous.world_position)
            ):
                raise RuntimeError(
                    f"Fit joint 朝向修改后复检失败：{current.short_name} 世界位置变化"
                )

        before_orient = {state.joint: state for state in plan.before.joints}
        after_orient = {state.joint: state for state in verified.joints}
        if set(before_orient) != set(after_orient):
            raise RuntimeError("Fit joint 朝向修改后复检失败：朝向快照不完整")
        changes = {change.joint: change for change in plan.changes}
        for path, state in after_orient.items():
            change = changes.get(path)
            if change is not None:
                if not orientation_matches(change, state):
                    raise RuntimeError(
                        f"Fit joint 朝向修改后复检失败：{path} 轴向不一致"
                    )
            elif state.joint_orient != before_orient[path].joint_orient:
                raise RuntimeError(
                    f"Fit joint 朝向修改后复检失败：{path} 被意外修改"
                )
