from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Mapping

from .body_limb_blend import BodyLimbBlendPlan
from .body_limb_stretch import BodyLimbStretchPlan
from .body_limb_twist import BodyLimbTwistPlan
from .fit_symmetry import FitBuildSide


class BodyLimbVolumeValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyLimbVolumeSideSpec:
    side: FitBuildSide
    attribute: str
    stretch_ratio_source: str
    mode_attribute: str
    mode_blend_name: str
    power_name: str
    blend_name: str
    exponent: float
    helper_joints: tuple[str, ...]
    helper_scale_axes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class BodyLimbVolumePlan:
    settings_path: str
    sides: tuple[BodyLimbVolumeSideSpec, ...]
    limb_label: str = "Arm"


@dataclass(frozen=True, slots=True)
class BodyLimbVolumeSideState:
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
    helper_scale_axes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class BodyLimbVolumeSnapshot:
    settings_path: str
    sides: tuple[BodyLimbVolumeSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbVolumeIssue:
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
        raise BodyLimbVolumeValidationError("Limb 体积保持比例或强度无效")
    preserved = 1.0 / sqrt(float(length_ratio))
    return 1.0 + (preserved - 1.0) * float(strength)


def plan_body_limb_volume(
    stretch: BodyLimbStretchPlan,
    twist: BodyLimbTwistPlan,
    blend: BodyLimbBlendPlan,
    *,
    limb_label: str,
    stretch_ratio_sources_by_side: Mapping[FitBuildSide, str] | None = None,
) -> BodyLimbVolumePlan:
    if (
        not isinstance(limb_label, str)
        or not limb_label.isalpha()
        or stretch.limb_label != limb_label
        or twist.limb_label != limb_label
    ):
        raise BodyLimbVolumeValidationError("Limb 体积保持定义不一致")

    sides = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        stretch_sides = tuple(spec for spec in stretch.sides if spec.side is side)
        blend_sides = tuple(spec for spec in blend.sides if spec.side is side)
        helper_specs = tuple(
            (spec.path, tuple(axis for axis in "XYZ" if axis != spec.axis))
            for spec in twist.joints
            if spec.side is side
        )
        helper_paths = tuple(path for path, _ in helper_specs)
        helper_axes = tuple(axes for _, axes in helper_specs)
        if (
            stretch.settings_path != blend.settings_path
            or len(stretch_sides) != 1
            or len(blend_sides) != 1
            or not helper_specs
            or len(set(helper_paths)) != len(helper_paths)
            or any(
                len(axes) != 2
                or axes[0] == axes[1]
                or any(axis not in "XYZ" for axis in axes)
                for axes in helper_axes
            )
        ):
            raise BodyLimbVolumeValidationError(
                f"{limb_label} 体积保持要求每侧唯一 stretch 输出和有效 twist helper"
            )
        stretch_side = stretch_sides[0]
        stretch_ratio_source = f"{stretch_side.blend_name}.outputR"
        if stretch_ratio_sources_by_side is not None:
            stretch_ratio_source = stretch_ratio_sources_by_side.get(side, "")
            if not isinstance(stretch_ratio_source, str) or not stretch_ratio_source:
                raise BodyLimbVolumeValidationError(
                    f"{limb_label} 体积保持缺少目标侧最终长度比例来源"
                )
        sides.append(BodyLimbVolumeSideSpec(
            side=side,
            attribute=f"{limb_label.lower()}Volume_{suffix}",
            stretch_ratio_source=stretch_ratio_source,
            mode_attribute=blend_sides[0].attribute,
            mode_blend_name=f"AdvPy_{limb_label}VolumeMode_{suffix}",
            power_name=f"AdvPy_{limb_label}VolumePower_{suffix}",
            blend_name=f"AdvPy_{limb_label}VolumeBlend_{suffix}",
            exponent=-0.5,
            helper_joints=helper_paths,
            helper_scale_axes=helper_axes,
        ))
    return BodyLimbVolumePlan(
        stretch.settings_path,
        tuple(sides),
        limb_label,
    )


def audit_body_limb_volume(
    plan: BodyLimbVolumePlan,
    snapshot: BodyLimbVolumeSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyLimbVolumeIssue, ...]:
    label = plan.limb_label
    issues = []
    if snapshot.settings_path != plan.settings_path:
        issues.append(BodyLimbVolumeIssue(
            "settings_mismatch",
            f"{label} 体积设置节点不一致",
        ))
    actual = {state.side: state for state in snapshot.sides}
    if set(actual) != {spec.side for spec in plan.sides}:
        issues.append(BodyLimbVolumeIssue(
            "side_set_mismatch",
            f"{label} 体积侧集合不一致",
        ))
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
            (
                state.attribute_plug == plug
                and abs(state.attribute_value - 1.0) <= tolerance,
                "attribute_mismatch",
                f"{label} 体积属性不一致",
            ),
            (
                state.mode_blend_name == spec.mode_blend_name
                and state.stretch_ratio_source == spec.stretch_ratio_source
                and state.mode_weight_source
                == f"{plan.settings_path}.{spec.mode_attribute}"
                and abs(state.mode_base_ratio - 1.0) <= tolerance,
                "mode_mismatch",
                f"{label} 体积 IK/FK 模式网络不一致",
            ),
            (
                state.power_name == spec.power_name
                and state.ratio_source == f"{spec.mode_blend_name}.outputR"
                and abs(state.exponent - spec.exponent) <= tolerance
                and state.power_operation == 3,
                "power_mismatch",
                f"{label} 体积反平方根网络不一致",
            ),
            (
                state.blend_name == spec.blend_name
                and state.power_source == f"{spec.power_name}.outputX"
                and state.volume_source == plug
                and abs(state.base_scale - 1.0) <= tolerance,
                "blend_mismatch",
                f"{label} 体积强度混合网络不一致",
            ),
            (
                state.helper_scale_axes == spec.helper_scale_axes
                and state.helper_scale_sources == expected_helpers,
                "helper_wiring_mismatch",
                f"{label} 体积 helper 正交缩放连线不一致",
            ),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyLimbVolumeIssue(
                    code,
                    message,
                    spec.side.value,
                ))
    return tuple(issues)
