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
from adv_py.core.body_leg_stretch import (
    BodyLegStretchPlan,
    BodyLegStretchSnapshot,
    audit_body_leg_stretch,
    plan_body_leg_stretch,
)
from adv_py.core.body_leg_stretch_bias import (
    BodyLegStretchBiasPlan,
    BodyLegStretchBiasSnapshot,
    audit_body_leg_stretch_bias,
    plan_body_leg_stretch_bias,
)
from adv_py.core.body_leg_twist import (
    BodyLegTwistJointSpec,
    BodyLegTwistPlan,
    BodyLegTwistSegmentSpec,
    BodyLegTwistSnapshot,
    audit_body_leg_twist,
    plan_body_leg_twist,
)
from adv_py.core.body_leg_volume import (
    BodyLegVolumePlan,
    BodyLegVolumeSnapshot,
    audit_body_leg_volume,
    plan_body_leg_volume,
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
    def create_body_leg_stretch(self, plan: BodyLegStretchPlan) -> None: ...
    def capture_body_leg_stretch(self, plan: BodyLegStretchPlan) -> BodyLegStretchSnapshot: ...
    def create_body_leg_stretch_bias(self, plan: BodyLegStretchBiasPlan) -> None: ...
    def capture_body_leg_stretch_bias(self, plan: BodyLegStretchBiasPlan) -> BodyLegStretchBiasSnapshot: ...
    def prepare_body_leg_twist_runtime(self) -> None: ...
    def create_body_leg_twist_root(self, name: str) -> str: ...
    def create_body_leg_twist_segment(self, spec: BodyLegTwistSegmentSpec) -> None: ...
    def create_body_leg_twist_joint(self, spec: BodyLegTwistJointSpec) -> None: ...
    def capture_body_leg_twist(self, plan: BodyLegTwistPlan) -> BodyLegTwistSnapshot: ...
    def create_body_leg_volume(self, plan: BodyLegVolumePlan) -> None: ...
    def capture_body_leg_volume(self, plan: BodyLegVolumePlan) -> BodyLegVolumeSnapshot: ...
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
    stretch: BodyLegStretchPlan
    stretch_bias: BodyLegStretchBiasPlan
    twist: BodyLegTwistPlan
    volume: BodyLegVolumePlan
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
    stretch: BodyLegStretchSnapshot
    stretch_bias: BodyLegStretchBiasSnapshot
    twist: BodyLegTwistSnapshot
    volume: BodyLegVolumeSnapshot
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
        twist_joints_per_segment: int = 2,
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
        stretch = plan_body_leg_stretch(mechanisms, ik)
        stretch_bias = plan_body_leg_stretch_bias(stretch)
        twist = plan_body_leg_twist(
            safety.body,
            joints_per_segment=twist_joints_per_segment,
        )
        volume = plan_body_leg_volume(stretch, twist, blend)
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
        for side in stretch.sides:
            names.extend((
                side.start_name,
                side.distance_name,
                side.ratio_name,
                side.rest_scale_name,
                side.clamp_name,
                side.blend_name,
                side.segment_name,
            ))
        for side in stretch_bias.sides:
            names.extend((
                side.delta_name,
                side.candidates_name,
                side.weights_name,
                side.factors_name,
            ))
        names.append(twist.root_name)
        for spec in twist.segments:
            names.extend((
                spec.name,
                spec.constraint_name,
                spec.compose_name,
                spec.decompose_name,
                spec.quaternion_name,
            ))
        for spec in twist.joints:
            names.extend((
                spec.name,
                spec.constraint_name,
                spec.multiplier_name,
            ))
        for spec in volume.sides:
            names.extend((
                spec.mode_blend_name,
                spec.power_name,
                spec.blend_name,
            ))
        for side in foot.sides:
            names.extend(pivot.name for pivot in side.pivots)
            names.extend((
                side.toe_constraint_name,
                side.toe_offset_name,
                side.toe_control_name,
            ))
            names.extend(node.name for node in side.roll.nodes)
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
            stretch,
            stretch_bias,
            twist,
            volume,
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
        twist_joints_per_segment: int = 2,
        center_tolerance: float = 0.01,
    ) -> BodyLegRigBuildResult:
        plan = self.plan(
            container_name,
            body_root_name=body_root_name,
            control_radius=control_radius,
            pole_distance_scale=pole_distance_scale,
            twist_joints_per_segment=twist_joints_per_segment,
            center_tolerance=center_tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Leg Rig 构建预检失败，场景未修改：" + "；".join(plan.blockers)
            )
        self._host.prepare_body_leg_twist_runtime()
        with self._host.transaction("构建完整双腿 IK/FK"):
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

            self._host.create_body_leg_stretch(plan.stretch)
            stretch = self._host.capture_body_leg_stretch(plan.stretch)
            stretch_issues = audit_body_leg_stretch(plan.stretch, stretch)
            if stretch_issues:
                raise RuntimeError(
                    "Leg stretch 阶段复检失败："
                    + "；".join(issue.message for issue in stretch_issues)
                )

            self._host.create_body_leg_stretch_bias(plan.stretch_bias)
            stretch_bias = self._host.capture_body_leg_stretch_bias(
                plan.stretch_bias
            )
            bias_issues = audit_body_leg_stretch_bias(
                plan.stretch_bias,
                stretch_bias,
            )
            if bias_issues:
                raise RuntimeError(
                    "Leg stretch bias 阶段复检失败："
                    + "；".join(issue.message for issue in bias_issues)
                )
            stretch = self._host.capture_body_leg_stretch(plan.stretch)
            stretch_issues = audit_body_leg_stretch(
                plan.stretch,
                stretch,
                expected_segment_factor_sources_by_side={
                    spec.side: spec.factor_sources
                    for spec in plan.stretch_bias.sides
                },
            )
            if stretch_issues:
                raise RuntimeError(
                    "Leg stretch bias 构建后基础网络复检失败："
                    + "；".join(issue.message for issue in stretch_issues)
                )

            if (
                self._host.create_body_leg_twist_root(plan.twist.root_name)
                != plan.twist.root_path
            ):
                raise RuntimeError("Leg twist 根路径漂移")
            for spec in plan.twist.segments:
                self._host.create_body_leg_twist_segment(spec)
            for spec in plan.twist.joints:
                self._host.create_body_leg_twist_joint(spec)
            twist = self._host.capture_body_leg_twist(plan.twist)
            twist_issues = audit_body_leg_twist(plan.twist, twist)
            if twist_issues:
                raise RuntimeError(
                    "Leg twist 阶段复检失败："
                    + "；".join(issue.message for issue in twist_issues)
                )

            self._host.create_body_leg_volume(plan.volume)
            volume = self._host.capture_body_leg_volume(plan.volume)
            volume_issues = audit_body_leg_volume(plan.volume, volume)
            if volume_issues:
                raise RuntimeError(
                    "Leg 体积保持阶段复检失败："
                    + "；".join(issue.message for issue in volume_issues)
                )

            for spec in plan.foot.sides:
                self._host.create_body_leg_foot_side(spec)
            foot = self._host.capture_body_leg_foot(plan.foot)
            if audit_body_leg_foot(plan.foot, foot):
                raise RuntimeError("Leg Foot 阶段复检失败")
            ik = self._host.capture_body_leg_ik(plan.ik)
            if audit_body_leg_ik(
                plan.ik,
                ik,
                expected_handle_parent_by_side={
                    side.side: side.final_handle_parent_path
                    for side in plan.foot.sides
                },
                expected_ankle_source_by_side={
                    side.side: side.ankle_orientation_source_path
                    for side in plan.foot.sides
                },
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
            plan,
            mechanisms,
            fk,
            blend,
            ik,
            visibility,
            stretch,
            stretch_bias,
            twist,
            volume,
            foot,
            body,
        )
