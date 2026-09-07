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
from adv_py.core.body_leg_ik import (
    BodyLegIkIssue,
    BodyLegIkPlan,
    BodyLegIkSnapshot,
    audit_body_leg_ik,
    plan_body_leg_ik,
)
from adv_py.core.body_leg_foot import (
    BodyLegFootIssue,
    BodyLegFootPlan,
    BodyLegFootSnapshot,
    audit_body_leg_foot,
    plan_body_leg_foot,
)
from adv_py.core.body_leg_match import (
    BodyLegFkToIkPlan,
    BodyLegFkToIkSceneState,
    BodyLegMatchIssue,
    audit_body_leg_fk_to_ik_preflight,
    audit_body_leg_fk_to_ik_result,
    plan_body_leg_fk_to_ik,
)
from adv_py.core.body_leg_mechanisms import plan_body_leg_mechanisms
from adv_py.core.body_skeleton import (
    BodySkeletonIssue,
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyLegFkToIkHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_leg_ik(self, plan: BodyLegIkPlan) -> BodyLegIkSnapshot: ...
    def capture_body_leg_blend(self, plan: BodyLegBlendPlan) -> BodyLegBlendSnapshot: ...
    def capture_body_leg_foot(self, plan: BodyLegFootPlan) -> BodyLegFootSnapshot: ...
    def capture_body_leg_fk_to_ik_state(self, plan: BodyLegFkToIkPlan) -> BodyLegFkToIkSceneState: ...
    def apply_body_leg_fk_to_ik(self, plan: BodyLegFkToIkPlan) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class BodyLegFkToIkBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    ik: BodyLegIkPlan
    blend: BodyLegBlendPlan
    foot: BodyLegFootPlan
    match: BodyLegFkToIkPlan
    scene_state: BodyLegFkToIkSceneState
    provenance_issues: tuple[BodySkeletonIssue, ...]
    ik_issues: tuple[BodyLegIkIssue, ...]
    blend_issues: tuple[BodyLegBlendIssue, ...]
    foot_issues: tuple[BodyLegFootIssue, ...]
    match_issues: tuple[BodyLegMatchIssue, ...]
    other_blend_values: tuple[tuple[FitBuildSide, float], ...]

    @property
    def ready(self) -> bool:
        return not (
            self.provenance_issues
            or self.ik_issues
            or self.blend_issues
            or self.foot_issues
            or self.match_issues
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        issues = (
            *self.provenance_issues,
            *self.ik_issues,
            *self.blend_issues,
            *self.foot_issues,
            *self.match_issues,
        )
        return tuple(issue.message for issue in issues)


@dataclass(frozen=True, slots=True)
class BodyLegFkToIkResult:
    plan: BodyLegFkToIkBuildPlan
    body: BodySkeletonSnapshot
    blend: BodyLegBlendSnapshot


class MatchBodyLegFkToIk:
    def __init__(self, host: BodyLegFkToIkHost) -> None:
        self._host = host
        self._symmetry = PlanFitSymmetry(host)

    def plan(
        self,
        side: FitBuildSide,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        pole_distance_scale: float = 0.75,
        center_tolerance: float = 0.01,
    ) -> BodyLegFkToIkBuildPlan:
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
        ik = plan_body_leg_ik(
            body, mechanisms, pole_distance_scale=pole_distance_scale
        )
        blend = plan_body_leg_blend(body, mechanisms)
        foot = plan_body_leg_foot(body, ik)
        match = plan_body_leg_fk_to_ik(
            body,
            ik,
            blend,
            side,
            pole_distance_scale=pole_distance_scale,
        )
        ik_snapshot = self._host.capture_body_leg_ik(ik)
        blend_snapshot = self._host.capture_body_leg_blend(blend)
        ik_issues = audit_body_leg_ik(
            ik,
            ik_snapshot,
            check_initial_pose=False,
            expected_handle_parent_by_side={
                value.side: value.final_handle_parent_path
                for value in foot.sides
            },
            expected_ankle_source_by_side={
                value.side: value.ankle_orientation_source_path
                for value in foot.sides
            },
        )
        blend_issues = audit_body_leg_blend(
            blend, blend_snapshot, expected_attribute_value=None
        )
        foot_issues = audit_body_leg_foot(
            foot,
            self._host.capture_body_leg_foot(foot),
            check_initial_pose=False,
            expected_attribute_value=None,
        )
        state = self._host.capture_body_leg_fk_to_ik_state(match)
        match_issues = audit_body_leg_fk_to_ik_preflight(match, state)
        other = tuple(
            (value.side, value.attribute_value)
            for value in blend_snapshot.sides
            if value.side is not side
        )
        return BodyLegFkToIkBuildPlan(
            symmetry,
            body,
            ik,
            blend,
            foot,
            match,
            state,
            provenance,
            ik_issues,
            blend_issues,
            foot_issues,
            match_issues,
            other,
        )

    def apply(
        self,
        side: FitBuildSide,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        pole_distance_scale: float = 0.75,
        center_tolerance: float = 0.01,
    ) -> BodyLegFkToIkResult:
        plan = self.plan(
            side,
            container_name,
            body_root_name=body_root_name,
            pole_distance_scale=pole_distance_scale,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Leg FK→IK 匹配预检失败，场景未修改："
                + "；".join(plan.blockers)
            )
        with self._host.transaction(f"{side.value} Leg FK→IK 匹配"):
            if self._host.capture_body_leg_fk_to_ik_state(plan.match) != plan.scene_state:
                raise RuntimeError("Leg FK→IK 匹配执行前场景状态已变化")
            self._host.apply_body_leg_fk_to_ik(plan.match)
            body = self._host.capture_body_skeleton(body_root_name)
            blend = self._host.capture_body_leg_blend(plan.blend)
            target = next(value for value in blend.sides if value.side is side)
            issues = audit_body_leg_fk_to_ik_result(
                plan.match, body, target.attribute_value
            )
            current_other = tuple(
                (value.side, value.attribute_value)
                for value in blend.sides
                if value.side is not side
            )
            if current_other != plan.other_blend_values:
                issues += (BodyLegMatchIssue(
                    "other_side_changed", "Leg FK→IK 匹配改变了另一侧 blend"
                ),)
            if issues:
                raise RuntimeError(
                    "Leg FK→IK 匹配复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            container = plan.symmetry.source.hierarchy.container
            if (
                self._host.capture_fit_orientation(container)
                != plan.symmetry.source
                or self._host.read_fit_skeleton_settings(container)
                != plan.symmetry.settings
            ):
                raise RuntimeError("Leg FK→IK 匹配后 Fit 输入变化")
        return BodyLegFkToIkResult(plan, body, blend)
