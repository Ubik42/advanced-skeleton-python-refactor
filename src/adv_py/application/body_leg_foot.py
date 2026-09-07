from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_leg_foot import (
    BodyLegFootInputState,
    BodyLegFootIssue,
    BodyLegFootPlan,
    BodyLegFootSideSpec,
    BodyLegFootSnapshot,
    audit_body_leg_foot,
    audit_body_leg_foot_input,
    plan_body_leg_foot,
)
from adv_py.core.body_leg_ik import BodyLegIkIssue, audit_body_leg_ik, plan_body_leg_ik
from adv_py.core.body_leg_mechanisms import plan_body_leg_mechanisms
from adv_py.core.body_skeleton import (
    BodySkeletonIssue,
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyLegFootHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_leg_ik(self, plan): ...
    def capture_body_leg_foot_input(self, plan: BodyLegFootPlan) -> BodyLegFootInputState: ...
    def create_body_leg_foot_side(self, spec: BodyLegFootSideSpec) -> None: ...
    def capture_body_leg_foot(self, plan: BodyLegFootPlan) -> BodyLegFootSnapshot: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class BodyLegFootBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    foot: BodyLegFootPlan
    provenance_issues: tuple[BodySkeletonIssue, ...]
    ik_issues: tuple[BodyLegIkIssue, ...]
    input_issues: tuple[BodyLegFootIssue, ...]

    @property
    def ready(self) -> bool:
        return not (self.provenance_issues or self.ik_issues or self.input_issues)

    @property
    def blockers(self) -> tuple[str, ...]:
        issues = (*self.provenance_issues, *self.ik_issues, *self.input_issues)
        return tuple(
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in issues
        )


@dataclass(frozen=True, slots=True)
class BodyLegFootBuildResult:
    plan: BodyLegFootBuildPlan
    snapshot: BodyLegFootSnapshot


class BuildBodyLegFoot:
    """Extend an existing bilateral Maya-first Leg rig with reverse-foot pivots."""

    def __init__(self, host: BodyLegFootHost) -> None:
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
    ) -> BodyLegFootBuildPlan:
        symmetry = self._symmetry.execute(
            container_name, center_tolerance=center_tolerance
        )
        body = self._host.capture_body_skeleton(body_root_name)
        mechanisms = plan_body_leg_mechanisms(body)
        ik = plan_body_leg_ik(
            body,
            mechanisms,
            radius=control_radius,
            pole_distance_scale=pole_distance_scale,
        )
        foot = plan_body_leg_foot(body, ik)
        provenance = audit_body_provenance(
            oriented_body_provenance(
                symmetry.source.hierarchy.container, len(symmetry.instances)
            ),
            body.provenance,
        )
        ik_issues = audit_body_leg_ik(
            ik,
            self._host.capture_body_leg_ik(ik),
            check_initial_pose=False,
        )
        input_issues = audit_body_leg_foot_input(
            self._host.capture_body_leg_foot_input(foot)
        )
        return BodyLegFootBuildPlan(
            symmetry, body, foot, provenance, ik_issues, input_issues
        )

    def apply(self, container_name: str = "FitSkeleton", **kwargs) -> BodyLegFootBuildResult:
        plan = self.plan(container_name, **kwargs)
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Foot pivot 预检失败，场景未修改：" + "；".join(plan.blockers)
            )
        with self._host.transaction("创建双腿 Foot pivot 与显式 roll/bank"):
            for side in plan.foot.sides:
                self._host.create_body_leg_foot_side(side)
            snapshot = self._host.capture_body_leg_foot(plan.foot)
            issues = audit_body_leg_foot(plan.foot, snapshot)
            if issues:
                raise RuntimeError(
                    "Foot pivot 复检失败：" + "；".join(issue.message for issue in issues)
                )
            if self._host.capture_body_skeleton(
                kwargs.get("body_root_name", "Root_M")
            ) != plan.body:
                raise RuntimeError("Foot pivot 构建后 Body 发生变化")
            container = plan.symmetry.source.hierarchy.container
            if (
                self._host.capture_fit_orientation(container) != plan.symmetry.source
                or self._host.read_fit_skeleton_settings(container)
                != plan.symmetry.settings
            ):
                raise RuntimeError("Foot pivot 构建后 Fit 输入变化")
        return BodyLegFootBuildResult(plan, snapshot)
