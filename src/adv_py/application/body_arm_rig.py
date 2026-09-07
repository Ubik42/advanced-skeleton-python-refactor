from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_arm_blend import BodyArmBlendPlan, BodyArmBlendSnapshot, audit_body_arm_blend, plan_body_arm_blend
from adv_py.core.body_arm_ik import BodyArmIkPlan, BodyArmIkSnapshot, BodyArmIkSpec, audit_body_arm_ik, plan_body_arm_ik
from adv_py.core.body_arm_visibility import BodyArmVisibilityPlan, BodyArmVisibilitySnapshot, audit_body_arm_visibility, plan_body_arm_visibility
from adv_py.core.body_arm_stretch import BodyArmStretchPlan, BodyArmStretchSnapshot, audit_body_arm_stretch, plan_body_arm_stretch
from adv_py.core.body_arm_twist import BodyArmTwistJointSpec, BodyArmTwistPlan, BodyArmTwistSegmentSpec, BodyArmTwistSnapshot, audit_body_arm_twist, plan_body_arm_twist
from adv_py.core.body_arm_volume import BodyArmVolumePlan, BodyArmVolumeSnapshot, audit_body_arm_volume, plan_body_arm_volume
from adv_py.core.body_arm_mechanisms import BodyArmMechanismJointSpec, BodyArmMechanismPlan, BodyArmMechanismRole, BodyArmMechanismSnapshot, audit_body_arm_mechanisms, plan_body_arm_mechanisms
from adv_py.core.body_controls import BodyArmFkControlPlan, BodyArmFkControlSnapshot, BodyArmFkControlSpec, audit_body_arm_fk_controls, plan_body_arm_fk_controls
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.fit_settings import FitSkeletonValidationError
from .body_rebuild import BodyRebuildInspectionHost, BodyRebuildSafetyAudit, InspectBodyRebuildSafety


class BodyArmRigHost(BodyRebuildInspectionHost, Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_body_arm_mechanism_root(self, name: str) -> str: ...
    def create_body_arm_mechanism_joint(self, spec: BodyArmMechanismJointSpec) -> str: ...
    def capture_body_arm_mechanisms(self, plan: BodyArmMechanismPlan) -> BodyArmMechanismSnapshot: ...
    def create_body_control_root(self, name: str) -> str: ...
    def create_body_arm_fk_control(self, spec: BodyArmFkControlSpec) -> None: ...
    def capture_body_arm_fk_controls(self, plan: BodyArmFkControlPlan) -> BodyArmFkControlSnapshot: ...
    def create_body_arm_blend(self, plan: BodyArmBlendPlan) -> None: ...
    def capture_body_arm_blend(self, plan: BodyArmBlendPlan) -> BodyArmBlendSnapshot: ...
    def create_body_arm_ik_root(self, name: str) -> str: ...
    def create_body_arm_ik(self, spec: BodyArmIkSpec) -> None: ...
    def capture_body_arm_ik(self, plan: BodyArmIkPlan) -> BodyArmIkSnapshot: ...
    def create_body_arm_visibility(self, plan: BodyArmVisibilityPlan) -> None: ...
    def capture_body_arm_visibility(self, plan: BodyArmVisibilityPlan) -> BodyArmVisibilitySnapshot: ...
    def create_body_arm_stretch(self, plan: BodyArmStretchPlan) -> None: ...
    def capture_body_arm_stretch(self, plan: BodyArmStretchPlan) -> BodyArmStretchSnapshot: ...
    def prepare_body_arm_twist_runtime(self) -> None: ...
    def create_body_arm_twist_root(self, name: str) -> str: ...
    def create_body_arm_twist_segment(self, spec: BodyArmTwistSegmentSpec) -> None: ...
    def create_body_arm_twist_joint(self, spec: BodyArmTwistJointSpec) -> None: ...
    def capture_body_arm_twist(self, plan: BodyArmTwistPlan) -> BodyArmTwistSnapshot: ...
    def create_body_arm_volume(self, plan: BodyArmVolumePlan) -> None: ...
    def capture_body_arm_volume(self, plan: BodyArmVolumePlan) -> BodyArmVolumeSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyArmRigBuildPlan:
    safety: BodyRebuildSafetyAudit
    mechanisms: BodyArmMechanismPlan
    fk_controls: BodyArmFkControlPlan
    blend: BodyArmBlendPlan
    ik: BodyArmIkPlan
    visibility: BodyArmVisibilityPlan
    stretch: BodyArmStretchPlan
    twist: BodyArmTwistPlan
    volume: BodyArmVolumePlan
    name_collisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.safety.safe_to_replace and not self.name_collisions

    @property
    def blockers(self) -> tuple[str, ...]:
        values = [issue.message for issue in self.safety.issues]
        if self.name_collisions:
            values.append("场景中存在 Arm Rig 同名节点：" + "、".join(self.name_collisions))
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BodyArmRigBuildResult:
    plan: BodyArmRigBuildPlan
    mechanisms: BodyArmMechanismSnapshot
    fk_controls: BodyArmFkControlSnapshot
    blend: BodyArmBlendSnapshot
    ik: BodyArmIkSnapshot
    visibility: BodyArmVisibilitySnapshot
    stretch: BodyArmStretchSnapshot
    twist: BodyArmTwistSnapshot
    volume: BodyArmVolumeSnapshot
    body: BodySkeletonSnapshot


class BuildBodyArmRig:
    def __init__(self, host: BodyArmRigHost) -> None:
        self._host, self._inspector = host, InspectBodyRebuildSafety(host)

    def plan(self, container_name="FitSkeleton", *, body_root_name="Root_M", control_radius=1.5, pole_distance_scale=0.75, twist_joints_per_segment=2, center_tolerance=0.01) -> BodyArmRigBuildPlan:
        safety = self._inspector.execute(container_name, root_name=body_root_name, center_tolerance=center_tolerance)
        mechanisms = plan_body_arm_mechanisms(safety.body)
        fk_drivers = {spec.source_joint: spec.path for spec in mechanisms.joints if spec.role is BodyArmMechanismRole.FK}
        fk_controls = plan_body_arm_fk_controls(safety.body, radius=control_radius, driven_joint_by_source=fk_drivers)
        blend = plan_body_arm_blend(safety.body, mechanisms)
        ik = plan_body_arm_ik(safety.body, mechanisms, radius=control_radius, pole_distance_scale=pole_distance_scale)
        visibility = plan_body_arm_visibility(fk_controls, ik, blend)
        stretch = plan_body_arm_stretch(mechanisms, ik)
        twist = plan_body_arm_twist(safety.body, joints_per_segment=twist_joints_per_segment)
        volume = plan_body_arm_volume(stretch, twist, blend)
        names = [mechanisms.root_name, fk_controls.root_name, blend.settings_name, ik.root_name]
        names.extend(spec.name for spec in mechanisms.joints)
        for spec in fk_controls.controls: names.extend((spec.offset_name, spec.control_name, spec.constraint_name))
        for side in blend.sides:
            names.append(side.reverse_name)
            names.extend(j.constraint_name for j in side.joints)
            names.extend(j.translation_constraint_name for j in side.joints if j.translation_constraint_name)
        for spec in ik.limbs: names.extend((spec.wrist_offset_name, spec.wrist_control_name, spec.pole_offset_name, spec.pole_control_name, spec.handle_name, spec.pole_constraint_name, spec.wrist_constraint_name))
        for side in stretch.sides:
            names.extend((side.start_name, side.distance_name, side.ratio_name, side.clamp_name, side.blend_name, side.segment_name))
        names.append(twist.root_name)
        for spec in twist.segments:
            names.extend((spec.name, spec.constraint_name, spec.compose_name, spec.decompose_name, spec.quaternion_name))
        names.extend(spec.name for spec in twist.joints)
        names.extend(spec.constraint_name for spec in twist.joints)
        names.extend(spec.multiplier_name for spec in twist.joints)
        for spec in volume.sides:
            names.extend((spec.mode_blend_name, spec.power_name, spec.blend_name))
        collisions = tuple(sorted({path for name in names for path in self._host.find_name_collisions(name)}))
        return BodyArmRigBuildPlan(safety, mechanisms, fk_controls, blend, ik, visibility, stretch, twist, volume, collisions)

    def apply(self, container_name="FitSkeleton", *, body_root_name="Root_M", control_radius=1.5, pole_distance_scale=0.75, twist_joints_per_segment=2, center_tolerance=0.01) -> BodyArmRigBuildResult:
        plan = self.plan(container_name, body_root_name=body_root_name, control_radius=control_radius, pole_distance_scale=pole_distance_scale, twist_joints_per_segment=twist_joints_per_segment, center_tolerance=center_tolerance)
        if not plan.ready: raise FitSkeletonValidationError("Arm Rig 构建预检失败，场景未修改：" + "；".join(plan.blockers))
        self._host.prepare_body_arm_twist_runtime()
        with self._host.transaction("构建完整双臂 IK/FK"):
            if self._host.create_body_arm_mechanism_root(plan.mechanisms.root_name) != plan.mechanisms.root_path: raise RuntimeError("Arm mechanism 根路径漂移")
            for spec in plan.mechanisms.joints: self._host.create_body_arm_mechanism_joint(spec)
            mechanisms = self._host.capture_body_arm_mechanisms(plan.mechanisms)
            if audit_body_arm_mechanisms(plan.mechanisms, mechanisms): raise RuntimeError("Arm mechanism 阶段复检失败")
            if self._host.create_body_control_root(plan.fk_controls.root_name) != plan.fk_controls.root_path: raise RuntimeError("Arm FK 根路径漂移")
            for spec in plan.fk_controls.controls: self._host.create_body_arm_fk_control(spec)
            fk = self._host.capture_body_arm_fk_controls(plan.fk_controls)
            if audit_body_arm_fk_controls(plan.fk_controls, fk): raise RuntimeError("Arm FK 阶段复检失败")
            self._host.create_body_arm_blend(plan.blend); blend = self._host.capture_body_arm_blend(plan.blend)
            if audit_body_arm_blend(plan.blend, blend): raise RuntimeError("Arm blend 阶段复检失败")
            if self._host.create_body_arm_ik_root(plan.ik.root_name) != plan.ik.root_path: raise RuntimeError("Arm IK 根路径漂移")
            for spec in plan.ik.limbs: self._host.create_body_arm_ik(spec)
            ik = self._host.capture_body_arm_ik(plan.ik)
            if audit_body_arm_ik(plan.ik, ik): raise RuntimeError("Arm IK 阶段复检失败")
            self._host.create_body_arm_visibility(plan.visibility)
            visibility = self._host.capture_body_arm_visibility(plan.visibility)
            if audit_body_arm_visibility(plan.visibility, visibility): raise RuntimeError("Arm 控制显隐阶段复检失败")
            self._host.create_body_arm_stretch(plan.stretch)
            stretch = self._host.capture_body_arm_stretch(plan.stretch)
            stretch_issues = audit_body_arm_stretch(plan.stretch, stretch)
            if stretch_issues:
                raise RuntimeError("Arm stretch 阶段复检失败：" + "；".join(issue.message for issue in stretch_issues))
            if self._host.create_body_arm_twist_root(plan.twist.root_name) != plan.twist.root_path:
                raise RuntimeError("Arm twist 根路径漂移")
            for spec in plan.twist.segments:
                self._host.create_body_arm_twist_segment(spec)
            for spec in plan.twist.joints:
                self._host.create_body_arm_twist_joint(spec)
            twist = self._host.capture_body_arm_twist(plan.twist)
            twist_issues = audit_body_arm_twist(plan.twist, twist)
            if twist_issues:
                raise RuntimeError("Arm twist 阶段复检失败：" + "；".join(issue.message for issue in twist_issues))
            self._host.create_body_arm_volume(plan.volume)
            volume = self._host.capture_body_arm_volume(plan.volume)
            volume_issues = audit_body_arm_volume(plan.volume, volume)
            if volume_issues:
                raise RuntimeError("Arm 体积保持阶段复检失败：" + "；".join(issue.message for issue in volume_issues))
            body = self._host.capture_body_skeleton(body_root_name)
            if not _body_bind_pose_matches(plan.safety.body, body):
                raise RuntimeError("Arm Rig 绑定姿态下 Body 发生变化")
            container = plan.safety.symmetry.source.hierarchy.container
            if self._host.capture_fit_orientation(container) != plan.safety.symmetry.source or self._host.read_fit_skeleton_settings(container) != plan.safety.symmetry.settings: raise RuntimeError("Arm Rig 构建后 Fit 输入变化")
        return BodyArmRigBuildResult(plan, mechanisms, fk, blend, ik, visibility, stretch, twist, volume, body)


def _body_bind_pose_matches(expected: BodySkeletonSnapshot, actual: BodySkeletonSnapshot) -> bool:
    if expected.root != actual.root or expected.provenance != actual.provenance:
        return False
    wanted = {joint.path: joint for joint in expected.joints}
    current = {joint.path: joint for joint in actual.joints}
    if set(wanted) != set(current):
        return False
    for path, before in wanted.items():
        after = current[path]
        if (before.name, before.parent_path, before.side, before.label) != (after.name, after.parent_path, after.side, after.label):
            return False
        vectors = ((before.world_position, after.world_position), (before.rotation, after.rotation))
        vectors += tuple(zip(before.world_axes, after.world_axes))
        if any(any(abs(a - b) > 1e-4 for a, b in zip(left, right)) for left, right in vectors):
            return False
    return True
