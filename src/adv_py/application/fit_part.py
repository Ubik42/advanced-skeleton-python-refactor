"""Host boundary for materializing Fit-driven Part hierarchy plans."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.fit_part import (
    FitPartChildState,
    FitPartHierarchySnapshot,
    FitPartFinalPaths,
    FitPartJointSpec,
    FitPartJointState,
    FitPartReparentSpec,
    audit_fit_part_hierarchy,
    plan_fit_part_final_paths,
    rebase_body_snapshot_after_parts,
)
from .body_skeleton import BodySkeletonBuildPlan
from .body_rig_validation import body_bind_pose_matches


class FitPartHierarchyHost(Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...

    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def preflight_fit_part_hierarchy(
        self,
        joints: tuple[FitPartJointSpec, ...],
        reparents: tuple[FitPartReparentSpec, ...],
    ) -> None: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_fit_part_joint(self, spec: FitPartJointSpec) -> None: ...

    def reparent_fit_part_child(self, spec: FitPartReparentSpec) -> None: ...

    def capture_fit_part_joints(
        self, names: tuple[str, ...]
    ) -> tuple[FitPartJointState, ...]: ...

    def capture_fit_part_children(
        self, names: tuple[str, ...]
    ) -> tuple[FitPartChildState, ...]: ...

    def capture_fit_part_body_paths(
        self, names: tuple[str, ...]
    ) -> tuple[tuple[str, str], ...]: ...


@dataclass(frozen=True, slots=True)
class FitPartHierarchyResult:
    plan: BodySkeletonBuildPlan
    snapshot: FitPartHierarchySnapshot
    final_paths: FitPartFinalPaths
    body: BodySkeletonSnapshot


class BuildFitPartHierarchy:
    """Create planned Part influences and reparent their Body end joints.

    The host resolves nodes by unique name or stable Maya handle. Planned
    DAG paths describe the pre-reparent scene and become stale as children
    move, so they must not be used as write-time identifiers.
    """

    def __init__(self, host: FitPartHierarchyHost) -> None:
        self._host = host

    def apply(self, plan: BodySkeletonBuildPlan) -> FitPartHierarchyResult:
        if not plan.ready:
            raise ValueError("Fit Part 构建需要完整且无冲突的 Body 计划")
        if not plan.specs:
            raise ValueError("Fit Part 构建缺少 Body 关节")
        final_paths = plan_fit_part_final_paths(
            plan.specs, plan.fit_parts, plan.fit_part_reparents)
        body = self._host.capture_body_skeleton(plan.specs[0].name)
        actual = {state.path: state for state in body.joints}
        if set(actual) != {spec.path for spec in plan.specs}:
            raise ValueError("Fit Part 构建前 Body 拓扑与计划不一致")
        for spec in plan.specs:
            state = actual[spec.path]
            if (state.name != spec.name or state.parent_path != spec.parent_path
                    or any(abs(a - b) > 1e-4 for a, b in zip(
                        state.world_position, spec.world_position))
                    or state.deform_profile != spec.deform_profile
                    or state.skin_enabled != spec.skin_enabled
                    or state.rotation_order != spec.rotation_order
                    or state.segment_scale_compensate
                    != spec.segment_scale_compensate):
                raise ValueError("Fit Part 构建前 Body 数据已变化：" + spec.name)
        names = tuple(item.name for item in plan.fit_parts)
        if len(set(names)) != len(names):
            raise ValueError("Fit Part 计划存在重名关节")
        for name in names:
            if self._host.find_name_collisions(name):
                raise ValueError("Fit Part 名称已被场景占用：" + name)
        self._host.preflight_fit_part_hierarchy(
            plan.fit_parts, plan.fit_part_reparents)

        with self._host.transaction("构建 Fit Part 层级"):
            for spec in plan.fit_parts:
                self._host.create_fit_part_joint(spec)
            for spec in plan.fit_part_reparents:
                self._host.reparent_fit_part_child(spec)
            snapshot = FitPartHierarchySnapshot(
                self._host.capture_fit_part_joints(names),
                self._host.capture_fit_part_children(tuple(dict.fromkeys(
                    item.child_name for item in plan.fit_part_reparents))),
                self._host.capture_fit_part_body_paths(tuple(
                    spec.name for spec in plan.specs)),
            )
            issues = audit_fit_part_hierarchy(
                plan.fit_parts, plan.fit_part_reparents, snapshot,
                final_paths=final_paths)
            if issues:
                raise RuntimeError("Fit Part 写后复检失败：" + "；".join(issues))
            body_after = self._host.capture_body_skeleton(
                plan.specs[0].name)
            expected_body = rebase_body_snapshot_after_parts(body, final_paths)
            if not body_bind_pose_matches(expected_body, body_after):
                raise RuntimeError("Fit Part 改挂改变 Body 绑定姿态")
        return FitPartHierarchyResult(plan, snapshot, final_paths, body_after)
