from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_leg_blend import (
    BodyLegBlendPlan,
    BodyLegBlendSnapshot,
    audit_body_leg_blend,
    plan_body_leg_blend,
)
from adv_py.core.body_leg_mechanisms import (
    BodyLegMechanismIssue,
    BodyLegMechanismPlan,
    BodyLegMechanismSnapshot,
    audit_body_leg_mechanisms,
    plan_body_leg_mechanisms,
)
from adv_py.core.body_skeleton import (
    BodySkeletonIssue,
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyLegBlendHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...

    def capture_body_leg_mechanisms(
        self,
        plan: BodyLegMechanismPlan,
    ) -> BodyLegMechanismSnapshot: ...

    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_body_leg_blend(self, plan: BodyLegBlendPlan) -> None: ...

    def capture_body_leg_blend(
        self,
        plan: BodyLegBlendPlan,
    ) -> BodyLegBlendSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyLegBlendBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    mechanisms: BodyLegMechanismSnapshot
    blend: BodyLegBlendPlan
    provenance_issues: tuple[BodySkeletonIssue, ...]
    mechanism_issues: tuple[BodyLegMechanismIssue, ...]
    name_collisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not (
            self.provenance_issues
            or self.mechanism_issues
            or self.name_collisions
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        values = [issue.message for issue in self.provenance_issues]
        values.extend(issue.message for issue in self.mechanism_issues)
        if self.name_collisions:
            values.append(
                "场景中存在 Leg IK/FK 输出同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyLegBlendBuildResult:
    plan: BodyLegBlendBuildPlan
    snapshot: BodyLegBlendSnapshot


class BuildBodyLegBlend:
    def __init__(self, host: BodyLegBlendHost) -> None:
        self._host = host
        self._symmetry = PlanFitSymmetry(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyLegBlendBuildPlan:
        symmetry = self._symmetry.execute(
            container_name,
            center_tolerance=center_tolerance,
        )
        body = self._host.capture_body_skeleton(body_root_name)
        provenance_issues = audit_body_provenance(
            oriented_body_provenance(
                symmetry.source.hierarchy.container,
                len(symmetry.instances),
            ),
            body.provenance,
        )
        mechanism_plan = plan_body_leg_mechanisms(body)
        mechanisms = self._host.capture_body_leg_mechanisms(mechanism_plan)
        mechanism_issues = audit_body_leg_mechanisms(
            mechanism_plan,
            mechanisms,
        )
        blend = plan_body_leg_blend(body, mechanism_plan)
        names = [blend.settings_name]
        for side in blend.sides:
            names.append(side.reverse_name)
            names.extend(joint.constraint_name for joint in side.joints)
            names.extend(
                joint.translation_constraint_name
                for joint in side.joints
                if joint.translation_constraint_name
            )
        collisions = tuple(sorted({
            path
            for name in names
            for path in self._host.find_name_collisions(name)
        }))
        return BodyLegBlendBuildPlan(
            symmetry,
            body,
            mechanisms,
            blend,
            provenance_issues,
            mechanism_issues,
            collisions,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyLegBlendBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Leg IK/FK 输出预检失败，场景未修改："
                + "；".join(plan.blockers)
            )
        with self._host.transaction("连接双腿 IK/FK 输出"):
            self._host.create_body_leg_blend(plan.blend)
            snapshot = self._host.capture_body_leg_blend(plan.blend)
            issues = audit_body_leg_blend(plan.blend, snapshot)
            if issues:
                raise RuntimeError(
                    "Leg IK/FK 输出复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            container = plan.symmetry.source.hierarchy.container
            if (
                self._host.capture_fit_orientation(container)
                != plan.symmetry.source
                or self._host.read_fit_skeleton_settings(container)
                != plan.symmetry.settings
            ):
                raise RuntimeError("Leg IK/FK 输出构建后 Fit 输入变化")
        return BodyLegBlendBuildResult(plan, snapshot)
