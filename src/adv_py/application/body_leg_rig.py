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
from adv_py.core.body_leg_controls import (
    BodyLegFkControlPlan,
    BodyLegFkControlSnapshot,
    BodyLegFkControlSpec,
    audit_body_leg_fk_controls,
    plan_body_leg_fk_controls,
)
from adv_py.core.body_leg_ik import (
    BodyLegIkPlan,
    BodyLegIkSnapshot,
    BodyLegIkSpec,
    audit_body_leg_ik,
    plan_body_leg_ik,
)
from adv_py.core.body_leg_foot import (
    BodyLegFootPlan,
    BodyLegFootSideSpec,
    BodyLegFootSnapshot,
    audit_body_leg_foot,
    plan_body_leg_foot,
)
from adv_py.core.body_leg_mechanisms import (
    BodyLegMechanismJointSpec,
    BodyLegMechanismPlan,
    BodyLegMechanismRole,
    BodyLegMechanismSnapshot,
    audit_body_leg_mechanisms,
    plan_body_leg_mechanisms,
)
from adv_py.core.body_leg_visibility import (
    BodyLegVisibilityPlan,
    BodyLegVisibilitySnapshot,
    audit_body_leg_visibility,
    plan_body_leg_visibility,
)
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.fit_settings import FitSkeletonValidationError

from .body_rebuild import (
    BodyRebuildInspectionHost,
    BodyRebuildSafetyAudit,
    InspectBodyRebuildSafety,
)
from .body_rig_validation import body_bind_pose_matches


class BodyLegRigHost(BodyRebuildInspectionHost, Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_body_leg_mechanism_root(self, name: str) -> str: ...
    def create_body_leg_mechanism_joint(self, spec: BodyLegMechanismJointSpec) -> str: ...
    def capture_body_leg_mechanisms(self, plan: BodyLegMechanismPlan) -> BodyLegMechanismSnapshot: ...
    def create_body_control_root(self, name: str) -> str: ...
    def create_body_leg_fk_control(self, spec: BodyLegFkControlSpec) -> None: ...
    def capture_body_leg_fk_controls(self, plan: BodyLegFkControlPlan) -> BodyLegFkControlSnapshot: ...
    def create_body_leg_blend(self, plan: BodyLegBlendPlan) -> None: ...
    def capture_body_leg_blend(self, plan: BodyLegBlendPlan) -> BodyLegBlendSnapshot: ...
    def create_body_leg_ik_root(self, name: str) -> str: ...
    def create_body_leg_ik(self, spec: BodyLegIkSpec) -> None: ...
    def capture_body_leg_ik(self, plan: BodyLegIkPlan) -> BodyLegIkSnapshot: ...
    def create_body_leg_visibility(self, plan: BodyLegVisibilityPlan) -> None: ...
    def capture_body_leg_visibility(self, plan: BodyLegVisibilityPlan) -> BodyLegVisibilitySnapshot: ...
    def create_body_leg_foot_side(self, spec: BodyLegFootSideSpec) -> None: ...
    def capture_body_leg_foot(self, plan: BodyLegFootPlan) -> BodyLegFootSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyLegRigBuildPlan:
    safety: BodyRebuildSafetyAudit
    mechanisms: BodyLegMechanismPlan
    fk_controls: BodyLegFkControlPlan
    blend: BodyLegBlendPlan
    ik: BodyLegIkPlan
    visibility: BodyLegVisibilityPlan
    foot: BodyLegFootPlan
    name_collisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.safety.safe_to_replace and not self.name_collisions

    @property
    def blockers(self) -> tuple[str, ...]:
        values = [issue.message for issue in self.safety.issues]
        if self.name_collisions:
            values.append(
                "场景中存在 Leg Rig 同名节点：" + "、".join(self.name_collisions)
            )
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyLegRigBuildResult:
    plan: BodyLegRigBuildPlan
    mechanisms: BodyLegMechanismSnapshot
    fk_controls: BodyLegFkControlSnapshot
    blend: BodyLegBlendSnapshot
    ik: BodyLegIkSnapshot
    visibility: BodyLegVisibilitySnapshot
    foot: BodyLegFootSnapshot
    body: BodySkeletonSnapshot


class BuildBodyLegRig:
    """Build the current Maya-first bilateral Leg baseline in one transaction."""

    def __init__(self, host: BodyLegRigHost) -> None:
        self._host = host
        self._inspector = InspectBodyRebuildSafety(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        body_root_name: str = "Root_M",
        control_radius: float = 1.75,
        pole_distance_scale: float = 0.75,
        center_tolerance: float = 0.01,
    ) -> BodyLegRigBuildPlan:
        safety = self._inspector.execute(
            container_name,
            root_name=body_root_name,
            center_tolerance=center_tolerance,
        )
        mechanisms = plan_body_leg_mechanisms(safety.body)
        fk_drivers = {
            spec.source_joint: spec.path
            for spec in mechanisms.joints
            if spec.role is BodyLegMechanismRole.FK
        }
        fk_controls = plan_body_leg_fk_controls(
            safety.body,
            radius=control_radius,
            driven_joint_by_source=fk_drivers,
        )
        blend = plan_body_leg_blend(safety.body, mechanisms)
        ik = plan_body_leg_ik(
            safety.body,
            mechanisms,
            radius=control_radius,
            pole_distance_scale=pole_distance_scale,
        )
        visibility = plan_body_leg_visibility(fk_controls, ik, blend)
        foot = plan_body_leg_foot(safety.body, ik)
        names = [
            mechanisms.root_name,
            fk_controls.root_name,
            blend.settings_name,
            ik.root_name,
        ]
        names.extend(spec.name for spec in mechanisms.joints)
        for spec in fk_controls.controls:
            names.extend((spec.offset_name, spec.control_name, spec.constraint_name))
        for side in blend.sides:
            names.append(side.reverse_name)
            names.extend(joint.constraint_name for joint in side.joints)
            names.extend(
                joint.translation_constraint_name
                for joint in side.joints
                if joint.translation_constraint_name
            )
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
        for side in foot.sides:
            names.extend(pivot.name for pivot in side.pivots)
            names.extend(
                pivot.multiplier_name
                for pivot in side.pivots
                if pivot.multiplier_name
            )
        collisions = tuple(sorted({
            path
            for name in names
            for path in self._host.find_name_collisions(name)
        }))
        return BodyLegRigBuildPlan(
            safety,
            mechanisms,
            fk_controls,
            blend,
            ik,
            visibility,
            foot,
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
    ) -> BodyLegRigBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            control_radius=control_radius,
            pole_distance_scale=pole_distance_scale,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Leg Rig 构建预检失败，场景未修改：" + "；".join(plan.blockers)
            )
        with self._host.transaction("构建含 Foot 的双腿 IK/FK"):
            if (
                self._host.create_body_leg_mechanism_root(plan.mechanisms.root_name)
                != plan.mechanisms.root_path
            ):
                raise RuntimeError("Leg mechanism 根路径漂移")
            for spec in plan.mechanisms.joints:
                self._host.create_body_leg_mechanism_joint(spec)
            mechanisms = self._host.capture_body_leg_mechanisms(plan.mechanisms)
            if audit_body_leg_mechanisms(plan.mechanisms, mechanisms):
                raise RuntimeError("Leg mechanism 阶段复检失败")

            if (
                self._host.create_body_control_root(plan.fk_controls.root_name)
                != plan.fk_controls.root_path
            ):
                raise RuntimeError("Leg FK 根路径漂移")
            for spec in plan.fk_controls.controls:
                self._host.create_body_leg_fk_control(spec)
            fk = self._host.capture_body_leg_fk_controls(plan.fk_controls)
            if audit_body_leg_fk_controls(plan.fk_controls, fk):
                raise RuntimeError("Leg FK 阶段复检失败")

            self._host.create_body_leg_blend(plan.blend)
            blend = self._host.capture_body_leg_blend(plan.blend)
            if audit_body_leg_blend(plan.blend, blend):
                raise RuntimeError("Leg blend 阶段复检失败")

            if (
                self._host.create_body_leg_ik_root(plan.ik.root_name)
                != plan.ik.root_path
            ):
                raise RuntimeError("Leg IK 根路径漂移")
            for spec in plan.ik.limbs:
                self._host.create_body_leg_ik(spec)
            ik = self._host.capture_body_leg_ik(plan.ik)
            if audit_body_leg_ik(plan.ik, ik):
                raise RuntimeError("Leg IK 阶段复检失败")

            self._host.create_body_leg_visibility(plan.visibility)
            visibility = self._host.capture_body_leg_visibility(plan.visibility)
            if audit_body_leg_visibility(plan.visibility, visibility):
                raise RuntimeError("Leg 控制显隐阶段复检失败")

            for spec in plan.foot.sides:
                self._host.create_body_leg_foot_side(spec)
            foot = self._host.capture_body_leg_foot(plan.foot)
            if audit_body_leg_foot(plan.foot, foot):
                raise RuntimeError("Leg Foot 阶段复检失败")
            ik = self._host.capture_body_leg_ik(plan.ik)
            if audit_body_leg_ik(
                plan.ik,
                ik,
                check_handle_parent=False,
            ):
                raise RuntimeError("Leg Foot 构建后 IK 结构复检失败")

            body = self._host.capture_body_skeleton(body_root_name)
            if not body_bind_pose_matches(plan.safety.body, body):
                raise RuntimeError("Leg Rig 绑定姿态下 Body 发生变化")
            container = plan.safety.symmetry.source.hierarchy.container
            if (
                self._host.capture_fit_orientation(container)
                != plan.safety.symmetry.source
                or self._host.read_fit_skeleton_settings(container)
                != plan.safety.symmetry.settings
            ):
                raise RuntimeError("Leg Rig 构建后 Fit 输入变化")
        return BodyLegRigBuildResult(
            plan, mechanisms, fk, blend, ik, visibility, foot, body
        )
