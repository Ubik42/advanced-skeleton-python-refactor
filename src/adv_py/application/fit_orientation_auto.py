"""Update a Fit hierarchy with MEL's per-joint orientation dispatch."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from typing import Protocol

from adv_py.core.fit_hierarchy import audit_fit_hierarchy
from adv_py.core.fit_orientation import (
    FitOrientationChange,
    FitOrientationRequest,
    FitOrientationSnapshot,
    FitOrientationValidationError,
    FitWorldOrientationChange,
    orientation_matches,
    plan_simple_fit_orientations,
    plan_world_fit_orientations,
    world_orientation_matches,
)
from adv_py.core.fit_settings import FitSkeletonSettings, audit_fit_skeleton_settings


FitChange = FitOrientationChange | FitWorldOrientationChange


class FitOrientationAutoHost(Protocol):
    def capture_fit_orientation(self, container_name: str) -> FitOrientationSnapshot: ...
    def read_fit_skeleton_settings(self, container_name: str) -> FitSkeletonSettings: ...
    def orient_fit_joint(self, change: FitOrientationChange) -> None: ...
    def orient_world_fit_joint(self, change: FitWorldOrientationChange) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class FitOrientationAutoPlan:
    before: FitOrientationSnapshot
    before_settings: FitSkeletonSettings
    changes: tuple[FitChange, ...]


@dataclass(frozen=True, slots=True)
class FitOrientationAutoResult:
    plan: FitOrientationAutoPlan
    verified: FitOrientationSnapshot


class OrientFitJoints:
    """Dispatch Aim and worldOrient per joint in ancestor-first order."""

    def __init__(self, host: FitOrientationAutoHost) -> None:
        self._host = host

    def plan(
        self, request: FitOrientationRequest,
        container_name: str = "FitSkeleton",
    ) -> FitOrientationAutoPlan:
        before = self._host.capture_fit_orientation(container_name)
        settings = self._host.read_fit_skeleton_settings(before.hierarchy.container)
        issues = audit_fit_skeleton_settings(settings, require_complete=True)
        if issues:
            raise FitOrientationValidationError(
                "FitSkeleton 容器设置无效："
                + "；".join(issue.message for issue in issues)
            )
        nodes = {node.path: node for node in before.hierarchy.joints}
        by_name = {node.short_name: node for node in before.hierarchy.joints}
        metadata = {item.joint: item for item in before.metadata}
        if len(metadata) != len(nodes):
            raise FitOrientationValidationError("自动朝向需要完整的 Fit joint 元数据")
        simple: list[str] = []
        world: list[str] = []
        seen: set[str] = set()
        for name in request.joints:
            node = nodes.get(name) or by_name.get(name)
            if node is None:
                raise FitOrientationValidationError(f"朝向目标不在 FitSkeleton 中：{name}")
            if node.path in seen:
                raise FitOrientationValidationError(f"重复的朝向目标：{node.path}")
            seen.add(node.path)
            item = metadata[node.path]
            if item.world_orient_up is not None:
                world.append(node.path)
            elif item.world_orient_forward is not None:
                raise FitOrientationValidationError(
                    f"{node.short_name} 设置了 worldOrientForward，但缺少 worldOrientUp"
                )
            else:
                simple.append(node.path)
        simple_set = set(simple)
        selected = []
        for choice in request.child_selections:
            node = nodes.get(choice.joint) or by_name.get(choice.joint)
            if node is None:
                raise FitOrientationValidationError(
                    f"分支朝向父关节不在 FitSkeleton 中：{choice.joint}"
                )
            if node.path not in simple_set:
                raise FitOrientationValidationError(
                    f"{node.short_name} 不属于子级 Aim 朝向目标"
                )
            selected.append(choice)
        changes: list[FitChange] = []
        if simple:
            changes.extend(plan_simple_fit_orientations(
                before, FitOrientationRequest(tuple(simple), tuple(selected))
            ))
        if world:
            changes.extend(plan_world_fit_orientations(
                before, FitOrientationRequest(tuple(world))
            ))
        changes.sort(key=lambda item: (item.joint.count("|"), item.joint))
        return FitOrientationAutoPlan(before, settings, tuple(changes))

    def apply(
        self, request: FitOrientationRequest,
        container_name: str = "FitSkeleton",
    ) -> FitOrientationAutoResult:
        plan = self.plan(request, container_name)
        if not plan.changes:
            return FitOrientationAutoResult(plan, plan.before)
        with self._host.transaction(
            f"更新 {len(plan.changes)} 个 Fit joint 朝向"
        ):
            for change in plan.changes:
                if isinstance(change, FitWorldOrientationChange):
                    self._host.orient_world_fit_joint(change)
                else:
                    self._host.orient_fit_joint(change)
            verified = self._host.capture_fit_orientation(
                plan.before.hierarchy.container
            )
            settings = self._host.read_fit_skeleton_settings(
                plan.before.hierarchy.container
            )
            self._verify(plan, verified, settings)
        return FitOrientationAutoResult(plan, verified)

    @staticmethod
    def _verify(
        plan: FitOrientationAutoPlan,
        verified: FitOrientationSnapshot,
        settings: FitSkeletonSettings,
    ) -> None:
        issues = audit_fit_hierarchy(verified.hierarchy)
        if issues:
            raise RuntimeError(
                "Fit 朝向更新后层级无效："
                + "；".join(issue.message for issue in issues)
            )
        before = plan.before
        if settings != plan.before_settings or (
            verified.axis_configuration != before.axis_configuration
            or verified.fit_scale != before.fit_scale
        ):
            raise RuntimeError("Fit 朝向更新后容器设置发生变化")
        corrections = {
            change.joint: change.corrected_world_orient_forward
            for change in plan.changes
            if isinstance(change, FitWorldOrientationChange)
            and change.corrected_world_orient_forward is not None
        }
        expected_metadata = tuple(
            replace(item, world_orient_forward=corrections[item.joint])
            if item.joint in corrections else item
            for item in before.metadata
        )
        if verified.metadata != expected_metadata:
            raise RuntimeError("Fit 朝向更新后元数据与原版修正规则不符")
        old_nodes = {node.path: node for node in before.hierarchy.joints}
        new_nodes = {node.path: node for node in verified.hierarchy.joints}
        if set(old_nodes) != set(new_nodes):
            raise RuntimeError("Fit 朝向更新后关节集合发生变化")
        for path, old in old_nodes.items():
            new = new_nodes[path]
            if (old.short_name != new.short_name
                    or old.dag_parent != new.dag_parent
                    or any(abs(a - b) > 1e-5 for a, b in zip(
                        old.world_position, new.world_position))):
                raise RuntimeError(f"Fit 朝向更新后关节位置或层级变化：{path}")
        old_states = {item.joint: item for item in before.joints}
        new_states = {item.joint: item for item in verified.joints}
        if set(old_states) != set(new_states):
            raise RuntimeError("Fit 朝向更新后关节朝向快照不完整")
        changed = {change.joint: change for change in plan.changes}
        for path, state in new_states.items():
            change = changed.get(path)
            if isinstance(change, FitWorldOrientationChange):
                matches = world_orientation_matches(change, state)
            elif isinstance(change, FitOrientationChange):
                matches = orientation_matches(change, state)
            else:
                matches = state.joint_orient == old_states[path].joint_orient
            if not matches:
                raise RuntimeError(f"Fit 朝向更新后轴向不一致：{path}")
