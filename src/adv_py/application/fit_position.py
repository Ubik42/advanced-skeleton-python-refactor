from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_hierarchy import FitHierarchySnapshot, audit_fit_hierarchy
from adv_py.core.fit_position import (
    FitJointPositionChange,
    FitJointPositionPatch,
    FitPositionValidationError,
    plan_fit_joint_position_changes,
)
from adv_py.core.fit_settings import (
    FitSkeletonSettings,
    audit_fit_skeleton_settings,
)


class FitPositionHost(Protocol):
    def capture_fit_hierarchy(self, container_name: str) -> FitHierarchySnapshot: ...

    def read_fit_skeleton_settings(
        self, container_name: str
    ) -> FitSkeletonSettings: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def set_fit_joint_local_position(
        self,
        joint: str,
        position: tuple[float, float, float],
        changed_axes: tuple[str, ...],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class FitPositionEditPlan:
    before_hierarchy: FitHierarchySnapshot
    before_settings: FitSkeletonSettings
    changes: tuple[FitJointPositionChange, ...]


@dataclass(frozen=True, slots=True)
class FitPositionEditResult:
    plan: FitPositionEditPlan
    verified_hierarchy: FitHierarchySnapshot


class EditFitJointPositions:
    """Apply explicit local positions without selection or automatic unlocking."""

    def __init__(self, host: FitPositionHost) -> None:
        self._host = host

    def plan(
        self,
        patch: FitJointPositionPatch,
        container_name: str = "FitSkeleton",
    ) -> FitPositionEditPlan:
        hierarchy = self._host.capture_fit_hierarchy(container_name)
        settings = self._host.read_fit_skeleton_settings(hierarchy.container)
        setting_issues = audit_fit_skeleton_settings(settings, require_complete=True)
        if setting_issues:
            raise FitPositionValidationError(
                "FitSkeleton 容器设置无效："
                + "；".join(issue.message for issue in setting_issues)
            )
        changes = plan_fit_joint_position_changes(hierarchy, patch)
        return FitPositionEditPlan(hierarchy, settings, changes)

    def apply(
        self,
        patch: FitJointPositionPatch,
        container_name: str = "FitSkeleton",
    ) -> FitPositionEditResult:
        plan = self.plan(patch, container_name)
        if not plan.changes:
            return FitPositionEditResult(plan, plan.before_hierarchy)

        with self._host.transaction(
            f"更新 {len(plan.changes)} 个 Fit joint 位置"
        ):
            for change in plan.changes:
                self._host.set_fit_joint_local_position(
                    change.joint,
                    change.after,
                    change.changed_axes,
                )
            hierarchy = self._host.capture_fit_hierarchy(
                plan.before_hierarchy.container
            )
            settings = self._host.read_fit_skeleton_settings(
                plan.before_hierarchy.container
            )
            self._verify(plan, hierarchy, settings)
        return FitPositionEditResult(plan, hierarchy)

    @staticmethod
    def _verify(
        plan: FitPositionEditPlan,
        hierarchy: FitHierarchySnapshot,
        settings: FitSkeletonSettings,
    ) -> None:
        issues = audit_fit_hierarchy(hierarchy)
        if issues:
            raise RuntimeError(
                "Fit joint 位置修改后复检失败："
                + "；".join(issue.message for issue in issues)
            )
        if settings != plan.before_settings:
            raise RuntimeError("Fit joint 位置修改后复检失败：容器设置被意外改写")

        before = {node.path: node for node in plan.before_hierarchy.joints}
        after = {node.path: node for node in hierarchy.joints}
        if set(before) != set(after):
            raise RuntimeError("Fit joint 位置修改后复检失败：层级节点集合发生变化")
        changes = {change.joint: change for change in plan.changes}
        for path, previous in before.items():
            current = after[path]
            expected_position = changes.get(path, None)
            wanted = (
                expected_position.after
                if expected_position is not None
                else previous.local_position
            )
            if any(abs(a - b) > 1e-6 for a, b in zip(current.local_position, wanted)):
                raise RuntimeError(
                    f"Fit joint 位置修改后复检失败：{current.short_name} 位置不一致"
                )
            if (
                current.short_name != previous.short_name
                or current.dag_parent != previous.dag_parent
                or current.locked_translation_axes
                != previous.locked_translation_axes
                or current.writable_translation_axes
                != previous.writable_translation_axes
            ):
                raise RuntimeError(
                    f"Fit joint 位置修改后复检失败：{current.short_name} 状态发生变化"
                )
