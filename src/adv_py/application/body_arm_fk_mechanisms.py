from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_arm_mechanisms import (
    BodyArmMechanismIssue,
    BodyArmMechanismPlan,
    BodyArmMechanismRole,
    BodyArmMechanismSnapshot,
    audit_body_arm_mechanisms,
    plan_body_arm_mechanisms,
)
from adv_py.core.body_controls import (
    BodyArmFkControlPlan,
    BodyArmFkControlSnapshot,
    BodyArmFkControlSpec,
    audit_body_arm_fk_controls,
    plan_body_arm_fk_controls,
)
from adv_py.core.body_skeleton import (
    BodySkeletonIssue,
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)
from adv_py.core.fit_settings import FitSkeletonValidationError

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyArmFkMechanismHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...

    def capture_body_arm_mechanisms(
        self,
        plan: BodyArmMechanismPlan,
    ) -> BodyArmMechanismSnapshot: ...

    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_body_control_root(self, name: str) -> str: ...

    def create_body_arm_fk_control(self, spec: BodyArmFkControlSpec) -> None: ...

    def capture_body_arm_fk_controls(
        self,
        plan: BodyArmFkControlPlan,
    ) -> BodyArmFkControlSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyArmFkMechanismBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    mechanisms: BodyArmMechanismSnapshot
    controls: BodyArmFkControlPlan
    provenance_issues: tuple[BodySkeletonIssue, ...]
    mechanism_issues: tuple[BodyArmMechanismIssue, ...]
    name_collisions: tuple[str, ...]

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers = [
            issue.message + (f"：{issue.joint}" if issue.joint else "")
            for issue in self.provenance_issues
        ]
        blockers.extend(
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in self.mechanism_issues
        )
        if self.name_collisions:
            blockers.append(
                "场景中存在 Arm FK 控制同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(blockers)

    @property
    def ready(self) -> bool:
        return not (
            self.provenance_issues
            or self.mechanism_issues
            or self.name_collisions
        )


@dataclass(frozen=True, slots=True)
class BodyArmFkMechanismBuildResult:
    plan: BodyArmFkMechanismBuildPlan
    snapshot: BodyArmFkControlSnapshot


class BuildBodyArmFkMechanismControls:
    """Create FK controls that drive validated FK mechanism joints."""

    def __init__(self, host: BodyArmFkMechanismHost) -> None:
        self._host = host
        self._symmetry = PlanFitSymmetry(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        control_radius: float = 1.5,
        center_tolerance: float = 0.01,
    ) -> BodyArmFkMechanismBuildPlan:
        symmetry = self._symmetry.execute(
            container_name,
            center_tolerance=center_tolerance,
        )
        body = self._host.capture_body_skeleton(body_root_name)
        expected_provenance = oriented_body_provenance(
            symmetry.source.hierarchy.container,
            len(symmetry.instances),
        )
        provenance_issues = audit_body_provenance(
            expected_provenance,
            body.provenance,
        )
        mechanism_plan = plan_body_arm_mechanisms(body)
        mechanisms = self._host.capture_body_arm_mechanisms(mechanism_plan)
        mechanism_issues = audit_body_arm_mechanisms(
            mechanism_plan,
            mechanisms,
        )
        fk_drivers = {
            spec.source_joint: spec.path
            for spec in mechanism_plan.joints
            if spec.role is BodyArmMechanismRole.FK
        }
        controls = plan_body_arm_fk_controls(
            body,
            radius=control_radius,
            driven_joint_by_source=fk_drivers,
        )
        names = [controls.root_name]
        for spec in controls.controls:
            names.extend((spec.offset_name, spec.control_name, spec.constraint_name))
        collisions = tuple(
            sorted(
                {
                    path
                    for name in names
                    for path in self._host.find_name_collisions(name)
                }
            )
        )
        return BodyArmFkMechanismBuildPlan(
            symmetry,
            body,
            mechanisms,
            controls,
            provenance_issues,
            mechanism_issues,
            collisions,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        control_radius: float = 1.5,
        center_tolerance: float = 0.01,
    ) -> BodyArmFkMechanismBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            control_radius=control_radius,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Arm FK 机制控制构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        with self._host.transaction("创建双臂 FK 机制控制"):
            root = self._host.create_body_control_root(plan.controls.root_name)
            if root != plan.controls.root_path:
                raise RuntimeError("Arm FK 控制根路径发生漂移")
            for spec in plan.controls.controls:
                self._host.create_body_arm_fk_control(spec)
            snapshot = self._host.capture_body_arm_fk_controls(plan.controls)
            issues = audit_body_arm_fk_controls(plan.controls, snapshot)
            if issues:
                raise RuntimeError(
                    "Arm FK 机制控制构建后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            if self._host.capture_body_skeleton(body_root_name) != plan.body:
                raise RuntimeError("Arm FK 机制控制构建后复检失败：Body 发生变化")
            expected_mechanisms = plan_body_arm_mechanisms(plan.body)
            if self._host.capture_body_arm_mechanisms(expected_mechanisms) != plan.mechanisms:
                raise RuntimeError("Arm FK 机制控制构建后复检失败：机制链基准状态变化")
            container = plan.symmetry.source.hierarchy.container
            if self._host.capture_fit_orientation(container) != plan.symmetry.source:
                raise RuntimeError("Arm FK 机制控制构建后复检失败：Fit joints 被改写")
            if self._host.read_fit_skeleton_settings(container) != plan.symmetry.settings:
                raise RuntimeError("Arm FK 机制控制构建后复检失败：容器设置被改写")
        return BodyArmFkMechanismBuildResult(plan, snapshot)
