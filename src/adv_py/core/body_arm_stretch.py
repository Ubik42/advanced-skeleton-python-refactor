from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

from .body_arm_ik import BodyArmIkPlan
from .body_arm_mechanisms import BodyArmMechanismPlan, BodyArmMechanismRole
from .fit_symmetry import FitBuildSide


Vector3 = tuple[float, float, float]


class BodyArmStretchValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyArmStretchSideSpec:
    side: FitBuildSide
    attribute: str
    start_path: str
    start_name: str
    start_position: Vector3
    wrist_control_path: str
    distance_name: str
    ratio_name: str
    rest_scale_name: str
    clamp_name: str
    blend_name: str
    segment_name: str
    rest_length: float
    segment_joints: tuple[str, str]
    base_translations: tuple[float, float]


@dataclass(frozen=True, slots=True)
class BodyArmStretchPlan:
    settings_path: str
    global_scale_attribute: str
    global_scale_default: float
    sides: tuple[BodyArmStretchSideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmStretchSideState:
    side: FitBuildSide
    attribute_plug: str
    attribute_value: float
    start_path: str
    start_position: Vector3
    distance_name: str
    distance_sources: tuple[str | None, str | None]
    ratio_name: str
    ratio_distance_source: str | None
    rest_scale_name: str
    rest_length: float
    global_scale_source: str | None
    rest_scale_operation: int
    ratio_divisor_source: str | None
    ratio_operation: int
    clamp_name: str
    clamp_input_source: str | None
    clamp_minimum: float
    clamp_maximum: float
    blend_name: str
    blend_ratio_source: str | None
    blend_weight_source: str | None
    blend_base_value: float
    segment_name: str
    base_translations: tuple[float, float]
    segment_factor_sources: tuple[str | None, str | None]
    segment_destination_sources: tuple[str | None, str | None]
    segment_operation: int


@dataclass(frozen=True, slots=True)
class BodyArmStretchSnapshot:
    settings_path: str
    global_scale_plug: str
    global_scale_value: float
    sides: tuple[BodyArmStretchSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmStretchIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_arm_stretch(
    mechanisms: BodyArmMechanismPlan,
    ik: BodyArmIkPlan,
    *,
    alignment_tolerance: float = 1e-4,
) -> BodyArmStretchPlan:
    sides = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        joints = tuple(
            spec
            for spec in mechanisms.joints
            if spec.side is side and spec.role is BodyArmMechanismRole.IK
        )
        limbs = tuple(spec for spec in ik.limbs if spec.side is side)
        if len(joints) != 3 or len(limbs) != 1:
            raise BodyArmStretchValidationError("Arm stretch 要求每侧唯一的三关节 IK 链和 Wrist 控制")
        translations = []
        for parent, child in zip(joints, joints[1:]):
            delta = tuple(b - a for a, b in zip(parent.world_position, child.world_position))
            length = sqrt(sum(value * value for value in delta))
            local_x = sum(value * axis for value, axis in zip(delta, parent.world_axes[0]))
            if length <= 1e-6 or abs(abs(local_x) - length) > alignment_tolerance:
                raise BodyArmStretchValidationError("Arm stretch 只支持沿机制关节本地 X 的有效段长")
            translations.append(local_x)
        rest_length = sum(abs(value) for value in translations)
        start_name = f"AdvPy_ArmStretchStart_{suffix}"
        sides.append(BodyArmStretchSideSpec(
            side,
            f"armStretch_{suffix}",
            f"{mechanisms.root_path}|{start_name}",
            start_name,
            joints[0].world_position,
            limbs[0].wrist_control_path,
            f"AdvPy_ArmStretchDistance_{suffix}",
            f"AdvPy_ArmStretchRatio_{suffix}",
            f"AdvPy_ArmStretchRestScale_{suffix}",
            f"AdvPy_ArmStretchClamp_{suffix}",
            f"AdvPy_ArmStretchBlend_{suffix}",
            f"AdvPy_ArmStretchSegments_{suffix}",
            rest_length,
            (joints[1].path, joints[2].path),
            tuple(translations),
        ))
    return BodyArmStretchPlan(
        "|AdvPy_ArmSettings",
        "armGlobalScale",
        1.0,
        tuple(sides),
    )


def audit_body_arm_stretch(
    plan: BodyArmStretchPlan,
    snapshot: BodyArmStretchSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyArmStretchIssue, ...]:
    issues = []
    if snapshot.settings_path != plan.settings_path:
        issues.append(BodyArmStretchIssue("settings_mismatch", "Arm stretch 设置节点不一致"))
    expected_global_plug = f"{plan.settings_path}.{plan.global_scale_attribute}"
    if (
        snapshot.global_scale_plug != expected_global_plug
        or abs(snapshot.global_scale_value - plan.global_scale_default) > tolerance
    ):
        issues.append(BodyArmStretchIssue("global_scale_mismatch", "Arm stretch 全局比例输入不一致"))
    actual = {state.side: state for state in snapshot.sides}
    for spec in plan.sides:
        state = actual.get(spec.side)
        if state is None:
            issues.append(BodyArmStretchIssue("missing_side", "缺少 Arm stretch 侧", spec.side.value))
            continue
        plug = f"{plan.settings_path}.{spec.attribute}"
        checks = (
            (state.attribute_plug == plug and abs(state.attribute_value - 1.0) <= tolerance, "attribute_mismatch", "Arm stretch 属性不一致"),
            (state.start_path == spec.start_path and _close(state.start_position, spec.start_position, tolerance), "start_mismatch", "Arm stretch 起点不一致"),
            (state.distance_name == spec.distance_name and state.distance_sources == (f"{spec.start_path}.worldMatrix[0]", f"{spec.wrist_control_path}.worldMatrix[0]"), "distance_wiring", "Arm stretch 测距连线不一致"),
            (state.rest_scale_name == spec.rest_scale_name and abs(state.rest_length - spec.rest_length) <= tolerance and state.global_scale_source == expected_global_plug and state.rest_scale_operation == 1, "rest_scale_wiring", "Arm stretch 全局参考长度连线不一致"),
            (state.ratio_name == spec.ratio_name and state.ratio_distance_source == f"{spec.distance_name}.distance" and state.ratio_divisor_source == f"{spec.rest_scale_name}.outputX" and state.ratio_operation == 2, "ratio_wiring", "Arm stretch 比例连线不一致"),
            (state.clamp_name == spec.clamp_name and state.clamp_input_source == f"{spec.ratio_name}.outputX" and abs(state.clamp_minimum - 1.0) <= tolerance and state.clamp_maximum >= 1000.0, "clamp_wiring", "Arm stretch no-compression 连线不一致"),
            (state.blend_name == spec.blend_name and state.blend_ratio_source == f"{spec.clamp_name}.outputR" and state.blend_weight_source == plug and abs(state.blend_base_value - 1.0) <= tolerance, "blend_wiring", "Arm stretch 强度连线不一致"),
            (state.segment_name == spec.segment_name and _close(state.base_translations, spec.base_translations, tolerance), "segment_values", "Arm stretch 基准段长不一致"),
            (state.segment_factor_sources == (f"{spec.blend_name}.outputR", f"{spec.blend_name}.outputR"), "segment_factor_wiring", "Arm stretch 段长比例连线不一致"),
            (state.segment_destination_sources == (f"{spec.segment_name}.outputX", f"{spec.segment_name}.outputY") and state.segment_operation == 1, "segment_output_wiring", "Arm stretch 输出目标连线不一致"),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyArmStretchIssue(code, message, spec.side.value))
    return tuple(issues)


def _close(left, right, tolerance):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def compensated_stretch_ratio(
    world_distance: float,
    rest_length: float,
    global_scale: float,
) -> float:
    values = (world_distance, rest_length, global_scale)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or value <= 0.0
        for value in values
    ):
        raise BodyArmStretchValidationError("Arm stretch 距离、绑定长度和全局比例必须为正有限数值")
    return float(world_distance) / (float(rest_length) * float(global_scale))
