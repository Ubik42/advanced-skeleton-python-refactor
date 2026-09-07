from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_arm_blend import BodyArmBlendIssue, BodyArmBlendPlan, BodyArmBlendSnapshot, audit_body_arm_blend, plan_body_arm_blend
from adv_py.core.body_arm_ik import BodyArmIkIssue, BodyArmIkPlan, BodyArmIkSnapshot, audit_body_arm_ik, plan_body_arm_ik
from adv_py.core.body_arm_match import BodyArmFkToIkPlan, BodyArmFkToIkSceneState, BodyArmMatchIssue, audit_body_arm_fk_to_ik_preflight, audit_body_arm_fk_to_ik_result, plan_body_arm_fk_to_ik
from adv_py.core.body_arm_mechanisms import plan_body_arm_mechanisms
from adv_py.core.body_skeleton import BodySkeletonIssue, BodySkeletonSnapshot, audit_body_provenance, oriented_body_provenance
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyArmFkToIkHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_arm_ik(self, plan: BodyArmIkPlan) -> BodyArmIkSnapshot: ...
    def capture_body_arm_blend(self, plan: BodyArmBlendPlan) -> BodyArmBlendSnapshot: ...
    def capture_body_arm_fk_to_ik_state(self, plan: BodyArmFkToIkPlan) -> BodyArmFkToIkSceneState: ...
    def apply_body_arm_fk_to_ik(self, plan: BodyArmFkToIkPlan) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class BodyArmFkToIkBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    ik: BodyArmIkPlan
    blend: BodyArmBlendPlan
    match: BodyArmFkToIkPlan
    scene_state: BodyArmFkToIkSceneState
    provenance_issues: tuple[BodySkeletonIssue, ...]
    ik_issues: tuple[BodyArmIkIssue, ...]
    blend_issues: tuple[BodyArmBlendIssue, ...]
    match_issues: tuple[BodyArmMatchIssue, ...]
    other_blend_values: tuple[tuple[FitBuildSide, float], ...]

    @property
    def ready(self) -> bool:
        return not (self.provenance_issues or self.ik_issues or self.blend_issues or self.match_issues)

    @property
    def blockers(self) -> tuple[str, ...]:
        issues = (*self.provenance_issues, *self.ik_issues, *self.blend_issues, *self.match_issues)
        return tuple(issue.message for issue in issues)


@dataclass(frozen=True, slots=True)
class BodyArmFkToIkResult:
    plan: BodyArmFkToIkBuildPlan
    body: BodySkeletonSnapshot
    blend: BodyArmBlendSnapshot


class MatchBodyArmFkToIk:
    def __init__(self, host: BodyArmFkToIkHost) -> None:
        self._host, self._symmetry = host, PlanFitSymmetry(host)

    def plan(self, side: FitBuildSide, container_name="FitSkeleton", *, body_root_name="Root_M", pole_distance_scale=0.75, center_tolerance=0.01) -> BodyArmFkToIkBuildPlan:
        symmetry = self._symmetry.execute(container_name, center_tolerance=center_tolerance)
        body = self._host.capture_body_skeleton(body_root_name)
        provenance = audit_body_provenance(oriented_body_provenance(symmetry.source.hierarchy.container, len(symmetry.instances)), body.provenance)
        mechanisms = plan_body_arm_mechanisms(body)
        ik = plan_body_arm_ik(body, mechanisms, pole_distance_scale=pole_distance_scale)
        blend = plan_body_arm_blend(body, mechanisms)
        match = plan_body_arm_fk_to_ik(body, ik, blend, side, pole_distance_scale=pole_distance_scale)
        ik_snapshot = self._host.capture_body_arm_ik(ik)
        blend_snapshot = self._host.capture_body_arm_blend(blend)
        ik_issues = audit_body_arm_ik(ik, ik_snapshot, check_initial_pose=False)
        blend_issues = audit_body_arm_blend(blend, blend_snapshot, expected_attribute_value=None)
        state = self._host.capture_body_arm_fk_to_ik_state(match)
        match_issues = audit_body_arm_fk_to_ik_preflight(match, state)
        other = tuple((value.side, value.attribute_value) for value in blend_snapshot.sides if value.side is not side)
        return BodyArmFkToIkBuildPlan(symmetry, body, ik, blend, match, state, provenance, ik_issues, blend_issues, match_issues, other)

    def apply(self, side: FitBuildSide, container_name="FitSkeleton", *, body_root_name="Root_M", pole_distance_scale=0.75, center_tolerance=0.01) -> BodyArmFkToIkResult:
        plan = self.plan(side, container_name, body_root_name=body_root_name, pole_distance_scale=pole_distance_scale, center_tolerance=center_tolerance)
        if not plan.ready:
            raise FitSkeletonValidationError("Arm FK→IK 匹配预检失败，场景未修改：" + "；".join(plan.blockers))
        with self._host.transaction(f"{side.value} Arm FK→IK 匹配"):
            if self._host.capture_body_arm_fk_to_ik_state(plan.match) != plan.scene_state:
                raise RuntimeError("Arm FK→IK 匹配执行前场景状态已变化")
            self._host.apply_body_arm_fk_to_ik(plan.match)
            body = self._host.capture_body_skeleton(body_root_name)
            blend = self._host.capture_body_arm_blend(plan.blend)
            target = next(value for value in blend.sides if value.side is side)
            issues = audit_body_arm_fk_to_ik_result(plan.match, body, target.attribute_value)
            current_other = tuple((value.side, value.attribute_value) for value in blend.sides if value.side is not side)
            if current_other != plan.other_blend_values:
                issues += (BodyArmMatchIssue("other_side_changed", "Arm FK→IK 匹配改变了另一侧 blend"),)
            if issues:
                raise RuntimeError("Arm FK→IK 匹配复检失败：" + "；".join(issue.message for issue in issues))
            container = plan.symmetry.source.hierarchy.container
            if self._host.capture_fit_orientation(container) != plan.symmetry.source or self._host.read_fit_skeleton_settings(container) != plan.symmetry.settings:
                raise RuntimeError("Arm FK→IK 匹配后 Fit 输入变化")
        return BodyArmFkToIkResult(plan, body, blend)
