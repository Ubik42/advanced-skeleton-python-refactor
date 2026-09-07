from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_leg_blend import audit_body_leg_blend, plan_body_leg_blend
from adv_py.core.body_leg_controls import audit_body_leg_fk_controls, plan_body_leg_fk_controls
from adv_py.core.body_leg_ik import audit_body_leg_ik, plan_body_leg_ik
from adv_py.core.body_leg_mechanisms import (
    BodyLegMechanismPlan,
    BodyLegMechanismRole,
    BodyLegMechanismSnapshot,
    audit_body_leg_mechanisms,
    plan_body_leg_mechanisms,
)
from adv_py.core.body_leg_visibility import (
    BodyLegVisibilityInputState,
    BodyLegVisibilityIssue,
    BodyLegVisibilityPlan,
    BodyLegVisibilitySnapshot,
    audit_body_leg_visibility,
    audit_body_leg_visibility_input,
    plan_body_leg_visibility,
)
from adv_py.core.body_skeleton import (
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyLegVisibilityHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_leg_mechanisms(self, plan: BodyLegMechanismPlan) -> BodyLegMechanismSnapshot: ...
    def capture_body_leg_fk_controls(self, plan): ...
    def capture_body_leg_ik(self, plan): ...
    def capture_body_leg_blend(self, plan): ...
    def capture_body_leg_visibility_input(self, plan: BodyLegVisibilityPlan) -> BodyLegVisibilityInputState: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_body_leg_visibility(self, plan: BodyLegVisibilityPlan) -> None: ...
    def capture_body_leg_visibility(self, plan: BodyLegVisibilityPlan) -> BodyLegVisibilitySnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyLegVisibilityBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    visibility: BodyLegVisibilityPlan
    dependency_blockers: tuple[str, ...]
    input_issues: tuple[BodyLegVisibilityIssue, ...]

    @property
    def ready(self) -> bool:
        return not (self.dependency_blockers or self.input_issues)

    @property
    def blockers(self) -> tuple[str, ...]:
        values = list(self.dependency_blockers)
        values.extend(
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in self.input_issues
        )
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyLegVisibilityBuildResult:
    plan: BodyLegVisibilityBuildPlan
    snapshot: BodyLegVisibilitySnapshot


class BuildBodyLegVisibility:
    """Connect an already-built bilateral Leg FK/IK rig to its mode attributes."""

    def __init__(self, host: BodyLegVisibilityHost) -> None:
        self._host = host
        self._symmetry = PlanFitSymmetry(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        control_radius: float = 1.75,
        pole_distance_scale: float = 0.75,
        center_tolerance: float = 0.01,
    ) -> BodyLegVisibilityBuildPlan:
        symmetry = self._symmetry.execute(container_name, center_tolerance=center_tolerance)
        body = self._host.capture_body_skeleton(body_root_name)
        mechanism_plan = plan_body_leg_mechanisms(body)
        mechanisms = self._host.capture_body_leg_mechanisms(mechanism_plan)
        fk_drivers = {
            spec.source_joint: spec.path
            for spec in mechanism_plan.joints
            if spec.role is BodyLegMechanismRole.FK
        }
        fk = plan_body_leg_fk_controls(body, radius=control_radius, driven_joint_by_source=fk_drivers)
        ik = plan_body_leg_ik(
            body,
            mechanism_plan,
            radius=control_radius,
            pole_distance_scale=pole_distance_scale,
        )
        blend = plan_body_leg_blend(body, mechanism_plan)
        visibility = plan_body_leg_visibility(fk, ik, blend)
        blockers = []
        expected_provenance = oriented_body_provenance(
            symmetry.source.hierarchy.container, len(symmetry.instances)
        )
        blockers.extend(issue.message for issue in audit_body_provenance(expected_provenance, body.provenance))
        blockers.extend(issue.message for issue in audit_body_leg_mechanisms(
            mechanism_plan, mechanisms, check_initial_pose=False
        ))
        blockers.extend(issue.message for issue in audit_body_leg_fk_controls(
            fk, self._host.capture_body_leg_fk_controls(fk), check_initial_pose=False
        ))
        blockers.extend(issue.message for issue in audit_body_leg_ik(
            ik, self._host.capture_body_leg_ik(ik), check_initial_pose=False
        ))
        blockers.extend(issue.message for issue in audit_body_leg_blend(
            blend, self._host.capture_body_leg_blend(blend), expected_attribute_value=None
        ))
        input_issues = audit_body_leg_visibility_input(
            visibility, self._host.capture_body_leg_visibility_input(visibility)
        )
        return BodyLegVisibilityBuildPlan(
            symmetry, body, visibility, tuple(blockers), input_issues
        )

    def apply(self, container_name: str = "FitSkeleton", **kwargs) -> BodyLegVisibilityBuildResult:
        plan = self.plan(container_name, **kwargs)
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Leg 控制显隐预检失败，场景未修改：" + "；".join(plan.blockers)
            )
        with self._host.transaction("连接双腿 FK/IK 控制显隐"):
            self._host.create_body_leg_visibility(plan.visibility)
            snapshot = self._host.capture_body_leg_visibility(plan.visibility)
            issues = audit_body_leg_visibility(plan.visibility, snapshot)
            if issues:
                raise RuntimeError(
                    "Leg 控制显隐复检失败：" + "；".join(issue.message for issue in issues)
                )
            if self._host.capture_body_skeleton(kwargs.get("body_root_name", "Root_M")) != plan.body:
                raise RuntimeError("Leg 控制显隐构建后 Body 发生变化")
            container = plan.symmetry.source.hierarchy.container
            if (
                self._host.capture_fit_orientation(container) != plan.symmetry.source
                or self._host.read_fit_skeleton_settings(container) != plan.symmetry.settings
            ):
                raise RuntimeError("Leg 控制显隐构建后 Fit 输入变化")
        return BodyLegVisibilityBuildResult(plan, snapshot)
