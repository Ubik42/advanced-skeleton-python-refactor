from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_arm_ik import BodyArmIkPlan, BodyArmIkSnapshot, BodyArmIkSpec, audit_body_arm_ik, plan_body_arm_ik
from adv_py.core.body_arm_mechanisms import BodyArmMechanismIssue, BodyArmMechanismPlan, BodyArmMechanismSnapshot, audit_body_arm_mechanisms, plan_body_arm_mechanisms
from adv_py.core.body_skeleton import BodySkeletonIssue, BodySkeletonSnapshot, audit_body_provenance, oriented_body_provenance
from adv_py.core.fit_settings import FitSkeletonValidationError
from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyArmIkHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...
    def capture_body_arm_mechanisms(self, plan: BodyArmMechanismPlan) -> BodyArmMechanismSnapshot: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_body_arm_ik_root(self, name: str) -> str: ...
    def create_body_arm_ik(self, spec: BodyArmIkSpec) -> None: ...
    def capture_body_arm_ik(self, plan: BodyArmIkPlan) -> BodyArmIkSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyArmIkBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    mechanisms: BodyArmMechanismSnapshot
    ik: BodyArmIkPlan
    provenance_issues: tuple[BodySkeletonIssue, ...]
    mechanism_issues: tuple[BodyArmMechanismIssue, ...]
    name_collisions: tuple[str, ...]

    @property
    def ready(self): return not (self.provenance_issues or self.mechanism_issues or self.name_collisions)
    @property
    def blockers(self):
        values = [issue.message for issue in self.provenance_issues]
        values.extend(issue.message for issue in self.mechanism_issues)
        if self.name_collisions: values.append("场景中存在 Arm IK 同名节点：" + "、".join(self.name_collisions))
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyArmIkBuildResult:
    plan: BodyArmIkBuildPlan
    snapshot: BodyArmIkSnapshot


class BuildBodyArmIkControls:
    def __init__(self, host: BodyArmIkHost):
        self._host, self._symmetry = host, PlanFitSymmetry(host)

    def plan(self, container_name="FitSkeleton", *, body_root_name="Root_M", control_radius=1.5, pole_distance_scale=0.75, center_tolerance=0.01):
        symmetry = self._symmetry.execute(container_name, center_tolerance=center_tolerance)
        body = self._host.capture_body_skeleton(body_root_name)
        provenance_issues = audit_body_provenance(oriented_body_provenance(symmetry.source.hierarchy.container, len(symmetry.instances)), body.provenance)
        mechanism_plan = plan_body_arm_mechanisms(body)
        mechanisms = self._host.capture_body_arm_mechanisms(mechanism_plan)
        mechanism_issues = audit_body_arm_mechanisms(mechanism_plan, mechanisms)
        ik = plan_body_arm_ik(body, mechanism_plan, radius=control_radius, pole_distance_scale=pole_distance_scale)
        names = [ik.root_name]
        for spec in ik.limbs:
            names.extend((spec.wrist_offset_name, spec.wrist_control_name, spec.pole_offset_name, spec.pole_control_name, spec.handle_name, spec.pole_constraint_name))
        collisions = tuple(sorted({path for name in names for path in self._host.find_name_collisions(name)}))
        return BodyArmIkBuildPlan(symmetry, body, mechanisms, ik, provenance_issues, mechanism_issues, collisions)

    def apply(self, container_name="FitSkeleton", *, body_root_name="Root_M", control_radius=1.5, pole_distance_scale=0.75, center_tolerance=0.01):
        plan = self.plan(container_name, body_root_name=body_root_name, control_radius=control_radius, pole_distance_scale=pole_distance_scale, center_tolerance=center_tolerance)
        if not plan.ready:
            raise FitSkeletonValidationError("Arm IK 构建预检失败，场景未修改：" + "；".join(plan.blockers))
        with self._host.transaction("创建双臂 RP IK 控制"):
            if self._host.create_body_arm_ik_root(plan.ik.root_name) != plan.ik.root_path:
                raise RuntimeError("Arm IK 控制根路径漂移")
            for spec in plan.ik.limbs: self._host.create_body_arm_ik(spec)
            snapshot = self._host.capture_body_arm_ik(plan.ik)
            issues = audit_body_arm_ik(plan.ik, snapshot)
            if issues: raise RuntimeError("Arm IK 构建后复检失败：" + "；".join(issue.message for issue in issues))
            if self._host.capture_body_skeleton(body_root_name) != plan.body: raise RuntimeError("Arm IK 构建后 Body 发生变化")
            current_mechanisms = self._host.capture_body_arm_mechanisms(
                plan_body_arm_mechanisms(plan.body)
            )
            before_by_path = {state.path: state for state in plan.mechanisms.joints}
            after_by_path = {state.path: state for state in current_mechanisms.joints}
            mechanism_structure_changed = set(before_by_path) != set(after_by_path)
            for path in set(before_by_path) & set(after_by_path):
                before, after = before_by_path[path], after_by_path[path]
                mechanism_structure_changed |= (
                    before.parent_path != after.parent_path
                    or before.side is not after.side
                    or before.source_joint != after.source_joint
                    or any(
                        abs(a - b) > 1e-4
                        for a, b in zip(before.world_position, after.world_position)
                    )
                )
            if mechanism_structure_changed:
                raise RuntimeError("Arm IK 构建后机制链结构或初始位置变化")
            container = plan.symmetry.source.hierarchy.container
            if self._host.capture_fit_orientation(container) != plan.symmetry.source: raise RuntimeError("Arm IK 构建后 Fit 被改写")
            if self._host.read_fit_skeleton_settings(container) != plan.symmetry.settings: raise RuntimeError("Arm IK 构建后容器设置被改写")
        return BodyArmIkBuildResult(plan, snapshot)
