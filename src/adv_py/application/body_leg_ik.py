from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_leg_ik import (
    BodyLegIkPlan,
    BodyLegIkSnapshot,
    BodyLegIkSpec,
    audit_body_leg_ik,
    plan_body_leg_ik,
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


class BodyLegIkHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...

    def capture_body_leg_mechanisms(
        self,
        plan: BodyLegMechanismPlan,
    ) -> BodyLegMechanismSnapshot: ...

    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_body_leg_ik_root(self, name: str) -> str: ...

    def create_body_leg_ik(self, spec: BodyLegIkSpec) -> None: ...

    def capture_body_leg_ik(self, plan: BodyLegIkPlan) -> BodyLegIkSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyLegIkBuildPlan:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    mechanisms: BodyLegMechanismSnapshot
    ik: BodyLegIkPlan
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
                "场景中存在 Leg IK 同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyLegIkBuildResult:
    plan: BodyLegIkBuildPlan
    snapshot: BodyLegIkSnapshot


class BuildBodyLegIkControls:
    def __init__(self, host: BodyLegIkHost) -> None:
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
    ) -> BodyLegIkBuildPlan:
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
        ik = plan_body_leg_ik(
            body,
            mechanism_plan,
            radius=control_radius,
            pole_distance_scale=pole_distance_scale,
        )
        names = [ik.root_name]
        for spec in ik.limbs:
            names.extend((
                spec.ankle_offset_name,
                spec.ankle_control_name,
                spec.pole_offset_name,
                spec.pole_control_name,
                spec.handle_name,
                spec.pole_constraint_name,
                spec.ankle_constraint_name,
            ))
        collisions = tuple(sorted({
            path
            for name in names
            for path in self._host.find_name_collisions(name)
        }))
        return BodyLegIkBuildPlan(
            symmetry,
            body,
            mechanisms,
            ik,
            provenance_issues,
            mechanism_issues,
            collisions,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        control_radius: float = 1.75,
        pole_distance_scale: float = 0.75,
        center_tolerance: float = 0.01,
    ) -> BodyLegIkBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            control_radius=control_radius,
            pole_distance_scale=pole_distance_scale,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Leg IK 构建预检失败，场景未修改："
                + "；".join(plan.blockers)
            )
        with self._host.transaction("创建双腿 RP IK 控制"):
            if (
                self._host.create_body_leg_ik_root(plan.ik.root_name)
                != plan.ik.root_path
            ):
                raise RuntimeError("Leg IK 控制根路径漂移")
            for spec in plan.ik.limbs:
                self._host.create_body_leg_ik(spec)
            snapshot = self._host.capture_body_leg_ik(plan.ik)
            issues = audit_body_leg_ik(plan.ik, snapshot)
            if issues:
                raise RuntimeError(
                    "Leg IK 构建后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
            if self._host.capture_body_skeleton(body_root_name) != plan.body:
                raise RuntimeError("Leg IK 构建后 Body 发生变化")
            current_mechanisms = self._host.capture_body_leg_mechanisms(
                plan_body_leg_mechanisms(plan.body)
            )
            if _mechanism_structure_changed(
                plan.mechanisms,
                current_mechanisms,
            ):
                raise RuntimeError("Leg IK 构建后机制链结构或初始位置变化")
            container = plan.symmetry.source.hierarchy.container
            if (
                self._host.capture_fit_orientation(container)
                != plan.symmetry.source
            ):
                raise RuntimeError("Leg IK 构建后 Fit 被改写")
            if (
                self._host.read_fit_skeleton_settings(container)
                != plan.symmetry.settings
            ):
                raise RuntimeError("Leg IK 构建后容器设置被改写")
        return BodyLegIkBuildResult(plan, snapshot)


def _mechanism_structure_changed(
    before: BodyLegMechanismSnapshot,
    after: BodyLegMechanismSnapshot,
    *,
    tolerance: float = 1e-4,
) -> bool:
    before_by_path = {state.path: state for state in before.joints}
    after_by_path = {state.path: state for state in after.joints}
    if set(before_by_path) != set(after_by_path):
        return True
    for path, previous in before_by_path.items():
        current = after_by_path[path]
        if (
            previous.parent_path != current.parent_path
            or previous.side is not current.side
            or previous.source_joint != current.source_joint
            or any(
                abs(a - b) > tolerance
                for a, b in zip(previous.world_position, current.world_position)
            )
        ):
            return True
    return False
