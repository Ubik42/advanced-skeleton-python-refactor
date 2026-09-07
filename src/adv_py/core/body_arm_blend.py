from __future__ import annotations

from dataclasses import dataclass

from .body_arm_mechanisms import BodyArmMechanismPlan, BodyArmMechanismRole
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import FitBuildSide


@dataclass(frozen=True, slots=True)
class BodyArmBlendJointSpec:
    body_joint: str
    fk_driver: str
    ik_driver: str
    constraint_name: str


@dataclass(frozen=True, slots=True)
class BodyArmBlendSideSpec:
    side: FitBuildSide
    attribute: str
    reverse_name: str
    joints: tuple[BodyArmBlendJointSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmBlendPlan:
    settings_path: str
    settings_name: str
    sides: tuple[BodyArmBlendSideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmBlendJointState:
    constraint_name: str
    body_joint: str | None
    targets: tuple[str, ...]
    fk_weight_source: str | None
    ik_weight_source: str | None


@dataclass(frozen=True, slots=True)
class BodyArmBlendSideState:
    side: FitBuildSide
    attribute_plug: str
    attribute_value: float
    reverse_name: str
    reverse_input_source: str | None
    joints: tuple[BodyArmBlendJointState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmBlendSnapshot:
    settings_path: str
    sides: tuple[BodyArmBlendSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmBlendIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_arm_blend(
    body: BodySkeletonSnapshot,
    mechanisms: BodyArmMechanismPlan,
) -> BodyArmBlendPlan:
    body_by_name = {joint.name: joint.path for joint in body.joints}
    sides = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        joints = []
        for part in ("Shoulder", "Elbow", "Wrist"):
            body_path = body_by_name[f"{part}_{suffix}"]
            fk = next(spec.path for spec in mechanisms.joints if spec.source_joint == body_path and spec.role is BodyArmMechanismRole.FK)
            ik = next(spec.path for spec in mechanisms.joints if spec.source_joint == body_path and spec.role is BodyArmMechanismRole.IK)
            joints.append(BodyArmBlendJointSpec(body_path, fk, ik, f"AdvPy_{part}IKFKBlend_{suffix}"))
        sides.append(BodyArmBlendSideSpec(side, f"armIkFk_{suffix}", f"AdvPy_ArmIKFKReverse_{suffix}", tuple(joints)))
    return BodyArmBlendPlan("|AdvPy_ArmSettings", "AdvPy_ArmSettings", tuple(sides))


def audit_body_arm_blend(plan: BodyArmBlendPlan, snapshot: BodyArmBlendSnapshot, *, expected_attribute_value: float | None = 0.0) -> tuple[BodyArmBlendIssue, ...]:
    issues = []
    if snapshot.settings_path != plan.settings_path:
        issues.append(BodyArmBlendIssue("settings_mismatch", "Arm IK/FK 设置节点不一致"))
    actual_sides = {state.side: state for state in snapshot.sides}
    for spec in plan.sides:
        state = actual_sides.get(spec.side)
        if state is None:
            issues.append(BodyArmBlendIssue("missing_side", "缺少 Arm IK/FK 侧", spec.side.value)); continue
        plug = f"{plan.settings_path}.{spec.attribute}"
        value_mismatch = expected_attribute_value is not None and abs(state.attribute_value - expected_attribute_value) > 1e-6
        if state.attribute_plug != plug or value_mismatch or state.reverse_name != spec.reverse_name or state.reverse_input_source != plug:
            issues.append(BodyArmBlendIssue("blend_driver_mismatch", "Arm IK/FK 属性或 reverse 连线不一致", spec.side.value))
        expected = {joint.constraint_name: joint for joint in spec.joints}
        actual = {joint.constraint_name: joint for joint in state.joints}
        if set(expected) != set(actual):
            issues.append(BodyArmBlendIssue("constraint_set_mismatch", "Arm IK/FK 约束集合不一致", spec.side.value)); continue
        for name, wanted in expected.items():
            current = actual[name]
            if current.body_joint != wanted.body_joint or current.targets != (wanted.fk_driver, wanted.ik_driver) or current.fk_weight_source != f"{spec.reverse_name}.outputX" or current.ik_weight_source != plug:
                issues.append(BodyArmBlendIssue("constraint_wiring_mismatch", "Arm IK/FK 双源权重连线不一致", name))
    return tuple(issues)
