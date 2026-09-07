from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_leg_blend import (
    BodyLegBlendIssue,
    BodyLegBlendPlan,
    BodyLegBlendSnapshot,
    audit_body_leg_blend,
    plan_body_leg_blend,
)
from adv_py.core.body_leg_controls import (
    BodyLegControlIssue,
    BodyLegFkControlPlan,
    BodyLegFkControlSnapshot,
    audit_body_leg_fk_controls,
    plan_body_leg_fk_controls,
)
from adv_py.core.body_leg_match import (
    BodyLegIkToFkPlan,
    BodyLegIkToFkSceneState,
    BodyLegMatchIssue,
    audit_body_leg_ik_to_fk_preflight,
    audit_body_leg_ik_to_fk_result,
    plan_body_leg_ik_to_fk,
)
from adv_py.core.body_leg_mechanisms import (
    BodyLegMechanismRole,
    plan_body_leg_mechanisms,
)
from adv_py.core.body_skeleton import (
    BodySkeletonIssue,
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyLegIkToFkHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_leg_fk_controls(self, plan: BodyLegFkControlPlan) -> BodyLegFkControlSnapshot: ...
    def capture_body_leg_blend(self, plan: BodyLegBlendPlan) -> BodyLegBlendSnapshot: ...
    def capture_body_leg_ik_to_fk_state(self, plan: BodyLegIkToFkPlan) -> BodyLegIkToFkSceneState: ...
    def apply_body_leg_ik_to_fk(self, plan: BodyLegIkToFkPlan) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class BodyLegIkToFkBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    fk_controls: BodyLegFkControlPlan
    blend: BodyLegBlendPlan
    match: BodyLegIkToFkPlan
    scene_state: BodyLegIkToFkSceneState
    provenance_issues: tuple[BodySkeletonIssue, ...]
    fk_issues: tuple[BodyLegControlIssue, ...]
    blend_issues: tuple[BodyLegBlendIssue, ...]
    match_issues: tuple[BodyLegMatchIssue, ...]
    other_blend_values: tuple[tuple[FitBuildSide, float], ...]

    @property
    def ready(self) -> bool:
        return not (
            self.provenance_issues
            or self.fk_issues
            or self.blend_issues
            or self.match_issues
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        issues = (
            *self.provenance_issues,
            *self.fk_issues,
            *self.blend_issues,
            *self.match_issues,
        )
        return tuple(issue.message for issue in issues)


@dataclass(frozen=True, slots=True)
class BodyLegIkToFkResult:
    plan: BodyLegIkToFkBuildPlan
    body: BodySkeletonSnapshot
    blend: BodyLegBlendSnapshot


class MatchBodyLegIkToFk:
    def __init__(self, host: BodyLegIkToFkHost) -> None:
        self._host = host
        self._symmetry = PlanFitSymmetry(host)

    def plan(
        self,
        side: FitBuildSide,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyLegIkToFkBuildPlan:
        symmetry = self._symmetry.execute(
            container_name, center_tolerance=center_tolerance
        )
        body = self._host.capture_body_skeleton(body_root_name)
        provenance = audit_body_provenance(
            oriented_body_provenance(
                symmetry.source.hierarchy.container, len(symmetry.instances)
            ),
            body.provenance,
        )
        mechanisms = plan_body_leg_mechanisms(body)
        fk_drivers = {
            spec.source_joint: spec.path
            for spec in mechanisms.joints
            if spec.role is BodyLegMechanismRole.FK
        }
        fk_controls = plan_body_leg_fk_controls(
            body, driven_joint_by_source=fk_drivers
        )
        blend = plan_body_leg_blend(body, mechanisms)
        match = plan_body_leg_ik_to_fk(body, fk_controls, blend, side)
        fk_snapshot = self._host.capture_body_leg_fk_controls(fk_controls)
        blend_snapshot = self._host.capture_body_leg_blend(blend)
        fk_issues = audit_body_leg_fk_controls(
            fk_controls, fk_snapshot, check_initial_pose=False
        )
        blend_issues = audit_body_leg_blend(
            blend, blend_snapshot, expected_attribute_value=None
        )
        state = self._host.capture_body_leg_ik_to_fk_state(match)
        match_issues = audit_body_leg_ik_to_fk_preflight(match, state)
        other = tuple(
            (value.side, value.attribute_value)
            for value in blend_snapshot.sides
            if value.side is not side
        )
        return BodyLegIkToFkBuildPlan(
            symmetry,
            body,
            fk_controls,
            blend,
            match,
            state,
            provenance,
            fk_issues,
            blend_issues,
            match_issues,
            other,
        )

    def apply(
        self,
        side: FitBuildSide,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyLegIkToFkResult:
        plan = self.plan(
            side,
            container_name,
            body_root_name=body_root_name,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Leg IK→FK 匹配预检失败，场景未修改："
                + "；".join(plan.blockers)
            )
        with self._host.transaction(f"{side.value} Leg IK→FK 匹配"):
            if self._host.capture_body_leg_ik_to_fk_state(plan.match) != plan.scene_state:
                raise RuntimeError("Leg IK→FK 匹配执行前场景状态已变化")
            self._host.apply_body_leg_ik_to_fk(plan.match)
            body = self._host.capture_body_skeleton(body_root_name)
            blend = self._host.capture_body_leg_blend(plan.blend)
            target = next(value for value in blend.sides if value.side is side)
            issues = audit_body_leg_ik_to_fk_result(
                plan.match, body, target.attribute_value
            )
            current_other = tuple(
                (value.side, value.attribute_value)
                for value in blend.sides
                if value.side is not side
            )
            if current_other != plan.other_blend_values:
                issues += (BodyLegMatchIssue(
                    "other_side_changed", "Leg IK→FK 匹配改变了另一侧 blend"
                ),)
            if issues:
                raise RuntimeError(
                    "Leg IK→FK 匹配复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            container = plan.symmetry.source.hierarchy.container
            if (
                self._host.capture_fit_orientation(container)
                != plan.symmetry.source
                or self._host.read_fit_skeleton_settings(container)
                != plan.symmetry.settings
            ):
                raise RuntimeError("Leg IK→FK 匹配后 Fit 输入变化")
        return BodyLegIkToFkResult(plan, body, blend)
