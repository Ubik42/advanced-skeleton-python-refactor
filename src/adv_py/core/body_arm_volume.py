from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

from .body_arm_blend import BodyArmBlendPlan
from .body_arm_stretch import BodyArmStretchPlan
from .body_arm_twist import BodyArmTwistPlan
from .fit_symmetry import FitBuildSide


class BodyArmVolumeValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyArmVolumeSideSpec:
    side: FitBuildSide
    attribute: str
    stretch_ratio_source: str
    mode_attribute: str
    mode_blend_name: str
    power_name: str
    blend_name: str
    exponent: float
    helper_joints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodyArmVolumePlan:
    settings_path: str
    sides: tuple[BodyArmVolumeSideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmVolumeSideState:
    side: FitBuildSide
    attribute_plug: str
    attribute_value: float
    mode_blend_name: str
    stretch_ratio_source: str | None
    mode_weight_source: str | None
    mode_base_ratio: float
    power_name: str
    ratio_source: str | None
    exponent: float
    power_operation: int
    blend_name: str
    power_source: str | None
    volume_source: str | None
    base_scale: float
    helper_scale_sources: tuple[tuple[str, str | None, str | None], ...]


@dataclass(frozen=True, slots=True)
class BodyArmVolumeSnapshot:
    settings_path: str
    sides: tuple[BodyArmVolumeSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmVolumeIssue:
    code: str
    message: str
    subject: str | None = None


def volume_preservation_scale(
    length_ratio: float,
    strength: float = 1.0,
) -> float:
    if (
        isinstance(length_ratio, bool)
        or not isinstance(length_ratio, (int, float))
        or not isfinite(length_ratio)
        or length_ratio <= 0.0
        or isinstance(strength, bool)
        or not isinstance(strength, (int, float))
        or not isfinite(strength)
        or not 0.0 <= strength <= 1.0
    ):
        raise BodyArmVolumeValidationError("Arm 体积保持比例或强度无效")
    preserved = 1.0 / sqrt(float(length_ratio))
    return 1.0 + (preserved - 1.0) * float(strength)


def plan_body_arm_volume(
    stretch: BodyArmStretchPlan,
    twist: BodyArmTwistPlan,
    blend: BodyArmBlendPlan,
) -> BodyArmVolumePlan:
    sides = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        stretch_sides = tuple(spec for spec in stretch.sides if spec.side is side)
        blend_sides = tuple(spec for spec in blend.sides if spec.side is side)
        helpers = tuple(spec.path for spec in twist.joints if spec.side is side)
        if (
            stretch.settings_path != blend.settings_path
            or len(stretch_sides) != 1
            or len(blend_sides) != 1
            or not helpers
        ):
            raise BodyArmVolumeValidationError(
                "Arm 体积保持要求每侧唯一 stretch 输出和非空 twist helper"
            )
        stretch_side = stretch_sides[0]
        sides.append(
            BodyArmVolumeSideSpec(
                side,
                f"armVolume_{suffix}",
                f"{stretch_side.blend_name}.outputR",
                blend_sides[0].attribute,
                f"AdvPy_ArmVolumeMode_{suffix}",
                f"AdvPy_ArmVolumePower_{suffix}",
                f"AdvPy_ArmVolumeBlend_{suffix}",
                -0.5,
                helpers,
            )
        )
    return BodyArmVolumePlan(stretch.settings_path, tuple(sides))


def audit_body_arm_volume(
    plan: BodyArmVolumePlan,
    snapshot: BodyArmVolumeSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyArmVolumeIssue, ...]:
    issues = []
    if snapshot.settings_path != plan.settings_path:
        issues.append(BodyArmVolumeIssue("settings_mismatch", "Arm 体积设置节点不一致"))
    actual = {state.side: state for state in snapshot.sides}
    if set(actual) != {spec.side for spec in plan.sides}:
        issues.append(BodyArmVolumeIssue("side_set_mismatch", "Arm 体积侧集合不一致"))
    for spec in plan.sides:
        state = actual.get(spec.side)
        if state is None:
            continue
        plug = f"{plan.settings_path}.{spec.attribute}"
        expected_helpers = tuple(
            (path, f"{spec.blend_name}.outputR", f"{spec.blend_name}.outputR")
            for path in spec.helper_joints
        )
        checks = (
            (state.attribute_plug == plug and abs(state.attribute_value - 1.0) <= tolerance, "attribute_mismatch", "Arm 体积属性不一致"),
            (state.mode_blend_name == spec.mode_blend_name and state.stretch_ratio_source == spec.stretch_ratio_source and state.mode_weight_source == f"{plan.settings_path}.{spec.mode_attribute}" and abs(state.mode_base_ratio - 1.0) <= tolerance, "mode_mismatch", "Arm 体积 IK/FK 模式网络不一致"),
            (state.power_name == spec.power_name and state.ratio_source == f"{spec.mode_blend_name}.outputR" and abs(state.exponent - spec.exponent) <= tolerance and state.power_operation == 3, "power_mismatch", "Arm 体积反平方根网络不一致"),
            (state.blend_name == spec.blend_name and state.power_source == f"{spec.power_name}.outputX" and state.volume_source == plug and abs(state.base_scale - 1.0) <= tolerance, "blend_mismatch", "Arm 体积强度混合网络不一致"),
            (state.helper_scale_sources == expected_helpers, "helper_wiring_mismatch", "Arm 体积 helper 横向缩放连线不一致"),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyArmVolumeIssue(code, message, spec.side.value))
    return tuple(issues)
