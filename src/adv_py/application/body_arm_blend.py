from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_arm_blend import BodyArmBlendPlan, BodyArmBlendSnapshot, audit_body_arm_blend, plan_body_arm_blend
from adv_py.core.body_arm_mechanisms import BodyArmMechanismIssue, BodyArmMechanismPlan, BodyArmMechanismSnapshot, audit_body_arm_mechanisms, plan_body_arm_mechanisms
from adv_py.core.body_skeleton import BodySkeletonIssue, BodySkeletonSnapshot, audit_body_provenance, oriented_body_provenance
from adv_py.core.fit_settings import FitSkeletonValidationError
from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyArmBlendHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_arm_mechanisms(self, plan: BodyArmMechanismPlan) -> BodyArmMechanismSnapshot: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_body_arm_blend(self, plan: BodyArmBlendPlan) -> None: ...
    def capture_body_arm_blend(self, plan: BodyArmBlendPlan) -> BodyArmBlendSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyArmBlendBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    mechanisms: BodyArmMechanismSnapshot
    blend: BodyArmBlendPlan
    provenance_issues: tuple[BodySkeletonIssue, ...]
    mechanism_issues: tuple[BodyArmMechanismIssue, ...]
    name_collisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not (self.provenance_issues or self.mechanism_issues or self.name_collisions)

    @property
    def blockers(self) -> tuple[str, ...]:
        values = [issue.message for issue in self.provenance_issues]
        values.extend(issue.message for issue in self.mechanism_issues)
        if self.name_collisions:
            values.append("场景中存在 Arm IK/FK 输出同名节点：" + "、".join(self.name_collisions))
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyArmBlendBuildResult:
    plan: BodyArmBlendBuildPlan
    snapshot: BodyArmBlendSnapshot


class BuildBodyArmBlend:
    def __init__(self, host: BodyArmBlendHost) -> None:
        self._host, self._symmetry = host, PlanFitSymmetry(host)

    def plan(self, container_name="FitSkeleton", *, body_root_name="Root_M", center_tolerance=0.01) -> BodyArmBlendBuildPlan:
        symmetry = self._symmetry.execute(container_name, center_tolerance=center_tolerance)
        body = self._host.capture_body_skeleton(body_root_name)
        provenance_issues = audit_body_provenance(oriented_body_provenance(symmetry.source.hierarchy.container, len(symmetry.instances)), body.provenance)
        mechanism_plan = plan_body_arm_mechanisms(body)
        mechanisms = self._host.capture_body_arm_mechanisms(mechanism_plan)
        mechanism_issues = audit_body_arm_mechanisms(mechanism_plan, mechanisms)
        blend = plan_body_arm_blend(body, mechanism_plan)
        names = [blend.settings_name]
        for side in blend.sides:
            names.append(side.reverse_name); names.extend(j.constraint_name for j in side.joints)
        collisions = tuple(sorted({path for name in names for path in self._host.find_name_collisions(name)}))
        return BodyArmBlendBuildPlan(symmetry, body, mechanisms, blend, provenance_issues, mechanism_issues, collisions)

    def apply(self, container_name="FitSkeleton", *, body_root_name="Root_M", center_tolerance=0.01) -> BodyArmBlendBuildResult:
        plan = self.plan(container_name, body_root_name=body_root_name, center_tolerance=center_tolerance)
        if not plan.ready:
            raise FitSkeletonValidationError("Arm IK/FK 输出预检失败，场景未修改：" + "；".join(plan.blockers))
        with self._host.transaction("连接双臂 IK/FK 输出"):
            self._host.create_body_arm_blend(plan.blend)
            snapshot = self._host.capture_body_arm_blend(plan.blend)
            issues = audit_body_arm_blend(plan.blend, snapshot)
            if issues:
                raise RuntimeError("Arm IK/FK 输出复检失败：" + "；".join(issue.message for issue in issues))
            container = plan.symmetry.source.hierarchy.container
            if self._host.capture_fit_orientation(container) != plan.symmetry.source or self._host.read_fit_skeleton_settings(container) != plan.symmetry.settings:
                raise RuntimeError("Arm IK/FK 输出构建后 Fit 输入变化")
        return BodyArmBlendBuildResult(plan, snapshot)
