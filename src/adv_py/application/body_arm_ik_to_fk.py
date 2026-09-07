from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_arm_blend import BodyArmBlendIssue, BodyArmBlendPlan, BodyArmBlendSnapshot, audit_body_arm_blend, plan_body_arm_blend
from adv_py.core.body_arm_match import BodyArmIkToFkPlan, BodyArmIkToFkSceneState, BodyArmMatchIssue, audit_body_arm_ik_to_fk_preflight, audit_body_arm_ik_to_fk_result, plan_body_arm_ik_to_fk
from adv_py.core.body_arm_mechanisms import BodyArmMechanismRole, plan_body_arm_mechanisms
from adv_py.core.body_controls import BodyArmFkControlPlan, BodyArmFkControlSnapshot, BodyControlIssue, audit_body_arm_fk_controls, plan_body_arm_fk_controls
from adv_py.core.body_skeleton import BodySkeletonIssue, BodySkeletonSnapshot, audit_body_provenance, oriented_body_provenance
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyArmIkToFkHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_arm_fk_controls(self, plan: BodyArmFkControlPlan) -> BodyArmFkControlSnapshot: ...
    def capture_body_arm_blend(self, plan: BodyArmBlendPlan) -> BodyArmBlendSnapshot: ...
    def capture_body_arm_ik_to_fk_state(self, plan: BodyArmIkToFkPlan) -> BodyArmIkToFkSceneState: ...
    def apply_body_arm_ik_to_fk(self, plan: BodyArmIkToFkPlan) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class BodyArmIkToFkBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    fk_controls: BodyArmFkControlPlan
    blend: BodyArmBlendPlan
    match: BodyArmIkToFkPlan
    scene_state: BodyArmIkToFkSceneState
    provenance_issues: tuple[BodySkeletonIssue, ...]
    fk_issues: tuple[BodyControlIssue, ...]
    blend_issues: tuple[BodyArmBlendIssue, ...]
    match_issues: tuple[BodyArmMatchIssue, ...]
    other_blend_values: tuple[tuple[FitBuildSide, float], ...]

    @property
    def ready(self) -> bool:
        return not (self.provenance_issues or self.fk_issues or self.blend_issues or self.match_issues)

    @property
    def blockers(self) -> tuple[str, ...]:
        issues = (*self.provenance_issues, *self.fk_issues, *self.blend_issues, *self.match_issues)
        return tuple(issue.message for issue in issues)


@dataclass(frozen=True, slots=True)
class BodyArmIkToFkResult:
    plan: BodyArmIkToFkBuildPlan
    body: BodySkeletonSnapshot
    blend: BodyArmBlendSnapshot


class MatchBodyArmIkToFk:
    def __init__(self, host: BodyArmIkToFkHost) -> None:
        self._host, self._symmetry = host, PlanFitSymmetry(host)

    def plan(self, side: FitBuildSide, container_name="FitSkeleton", *, body_root_name="Root_M", center_tolerance=0.01) -> BodyArmIkToFkBuildPlan:
        symmetry = self._symmetry.execute(container_name, center_tolerance=center_tolerance)
        body = self._host.capture_body_skeleton(body_root_name)
        provenance = audit_body_provenance(oriented_body_provenance(symmetry.source.hierarchy.container, len(symmetry.instances)), body.provenance)
        mechanisms = plan_body_arm_mechanisms(body)
        fk_drivers = {spec.source_joint: spec.path for spec in mechanisms.joints if spec.role is BodyArmMechanismRole.FK}
        fk_controls = plan_body_arm_fk_controls(body, driven_joint_by_source=fk_drivers)
        blend = plan_body_arm_blend(body, mechanisms)
        match = plan_body_arm_ik_to_fk(body, fk_controls, blend, side)
        fk_snapshot = self._host.capture_body_arm_fk_controls(fk_controls)
        blend_snapshot = self._host.capture_body_arm_blend(blend)
        fk_issues = audit_body_arm_fk_controls(fk_controls, fk_snapshot, check_initial_pose=False)
        blend_issues = audit_body_arm_blend(blend, blend_snapshot, expected_attribute_value=None)
        state = self._host.capture_body_arm_ik_to_fk_state(match)
        match_issues = audit_body_arm_ik_to_fk_preflight(match, state)
        other = tuple((value.side, value.attribute_value) for value in blend_snapshot.sides if value.side is not side)
        return BodyArmIkToFkBuildPlan(symmetry, body, fk_controls, blend, match, state, provenance, fk_issues, blend_issues, match_issues, other)

    def apply(self, side: FitBuildSide, container_name="FitSkeleton", *, body_root_name="Root_M", center_tolerance=0.01) -> BodyArmIkToFkResult:
        plan = self.plan(side, container_name, body_root_name=body_root_name, center_tolerance=center_tolerance)
        if not plan.ready:
            raise FitSkeletonValidationError("Arm IK→FK 匹配预检失败，场景未修改：" + "；".join(plan.blockers))
        with self._host.transaction(f"{side.value} Arm IK→FK 匹配"):
            if self._host.capture_body_arm_ik_to_fk_state(plan.match) != plan.scene_state:
                raise RuntimeError("Arm IK→FK 匹配执行前场景状态已变化")
            self._host.apply_body_arm_ik_to_fk(plan.match)
            body = self._host.capture_body_skeleton(body_root_name)
            blend = self._host.capture_body_arm_blend(plan.blend)
            match_state = self._host.capture_body_arm_ik_to_fk_state(plan.match)
            target = next(value for value in blend.sides if value.side is side)
            issues = audit_body_arm_ik_to_fk_result(
                plan.match,
                body,
                target.attribute_value,
                match_state.fk_segment_translations,
            )
            current_other = tuple((value.side, value.attribute_value) for value in blend.sides if value.side is not side)
            if current_other != plan.other_blend_values:
                issues += (BodyArmMatchIssue("other_side_changed", "Arm IK→FK 匹配改变了另一侧 blend"),)
            if issues:
                raise RuntimeError("Arm IK→FK 匹配复检失败：" + "；".join(issue.message for issue in issues))
            container = plan.symmetry.source.hierarchy.container
            if self._host.capture_fit_orientation(container) != plan.symmetry.source or self._host.read_fit_skeleton_settings(container) != plan.symmetry.settings:
                raise RuntimeError("Arm IK→FK 匹配后 Fit 输入变化")
        return BodyArmIkToFkResult(plan, body, blend)
