from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Mapping

from .body_limb_mechanisms import BodyLimbMechanismPlan, BodyLimbMechanismRole
from .fit_symmetry import FitBuildSide


Vector3 = tuple[float, float, float]


class BodyLimbStretchValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyLimbStretchSideSpec:
    side: FitBuildSide
    attribute: str
    start_path: str
    start_name: str
    start_position: Vector3
    target_control_path: str
    distance_name: str
    ratio_name: str
    rest_scale_name: str
    clamp_name: str
    blend_name: str
    segment_name: str
    rest_length: float
    segment_joints: tuple[str, str]
    base_translations: tuple[float, float]
    segment_channels: tuple[str, str] = ("X", "X")

    @property
    def wrist_control_path(self) -> str:
        """Compatibility name for the existing Arm public contract."""
        return self.target_control_path

    @property
    def ankle_control_path(self) -> str:
        return self.target_control_path


@dataclass(frozen=True, slots=True)
class BodyLimbStretchPlan:
    settings_path: str
    global_scale_attribute: str
    global_scale_default: float
    sides: tuple[BodyLimbStretchSideSpec, ...]
    limb_label: str = "Arm"


@dataclass(frozen=True, slots=True)
class BodyLimbStretchSideState:
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
class BodyLimbStretchSnapshot:
    settings_path: str
    global_scale_plug: str
    global_scale_value: float
    sides: tuple[BodyLimbStretchSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbStretchIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_limb_stretch(
    mechanisms: BodyLimbMechanismPlan,
    target_control_by_side: Mapping[FitBuildSide, str],
    *,
    limb_label: str,
    alignment_tolerance: float = 1e-4,
) -> BodyLimbStretchPlan:
    expected_sides = {FitBuildSide.RIGHT, FitBuildSide.LEFT}
    if (
        not isinstance(limb_label, str)
        or not limb_label.isalpha()
        or mechanisms.limb_label != limb_label
        or set(target_control_by_side) != expected_sides
        or any(
            not isinstance(path, str) or not path.startswith("|")
            for path in target_control_by_side.values()
        )
        or len(set(target_control_by_side.values())) != 2
        or isinstance(alignment_tolerance, bool)
        or not isinstance(alignment_tolerance, (int, float))
        or not isfinite(float(alignment_tolerance))
        or alignment_tolerance < 0.0
    ):
        raise BodyLimbStretchValidationError(
            f"{limb_label} stretch 输入定义无效"
        )

    sides = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        joints = tuple(
            spec
            for spec in mechanisms.joints
            if spec.side is side and spec.role is BodyLimbMechanismRole.IK
        )
        if len(joints) < 3:
            raise BodyLimbStretchValidationError(
                f"{limb_label} stretch 要求每侧至少三关节 IK 链"
            )
        driven_chain = joints[:3]
        if any(
            child.parent_path != parent.path
            for parent, child in zip(driven_chain, driven_chain[1:])
        ):
            raise BodyLimbStretchValidationError(
                f"{limb_label} stretch IK 链父级不连续"
            )
        translations = []
        channels = []
        for parent, child in zip(driven_chain, driven_chain[1:]):
            delta = tuple(
                child_value - parent_value
                for parent_value, child_value in zip(
                    parent.world_position, child.world_position
                )
            )
            length = sqrt(sum(value * value for value in delta))
            projections = tuple(
                sum(value * component for value, component in zip(delta, axis))
                for axis in parent.world_axes
            )
            axis_index = max(range(3), key=lambda index: abs(projections[index]))
            local_value = projections[axis_index]
            if (
                not isfinite(length)
                or not isfinite(local_value)
                or length <= 1e-6
                or abs(abs(local_value) - length) > alignment_tolerance
            ):
                raise BodyLimbStretchValidationError(
                    f"{limb_label} stretch 要求每段沿一个明确的关节本地主轴"
                )
            translations.append(local_value)
            channels.append("XYZ"[axis_index])
        rest_length = sum(abs(value) for value in translations)
        start_name = f"AdvPy_{limb_label}StretchStart_{suffix}"
        sides.append(BodyLimbStretchSideSpec(
            side=side,
            attribute=f"{limb_label.lower()}Stretch_{suffix}",
            start_path=f"{mechanisms.root_path}|{start_name}",
            start_name=start_name,
            start_position=driven_chain[0].world_position,
            target_control_path=target_control_by_side[side],
            distance_name=f"AdvPy_{limb_label}StretchDistance_{suffix}",
            ratio_name=f"AdvPy_{limb_label}StretchRatio_{suffix}",
            rest_scale_name=f"AdvPy_{limb_label}StretchRestScale_{suffix}",
            clamp_name=f"AdvPy_{limb_label}StretchClamp_{suffix}",
            blend_name=f"AdvPy_{limb_label}StretchBlend_{suffix}",
            segment_name=f"AdvPy_{limb_label}StretchSegments_{suffix}",
            rest_length=rest_length,
            segment_joints=(driven_chain[1].path, driven_chain[2].path),
            base_translations=tuple(translations),
            segment_channels=tuple(channels),
        ))
    return BodyLimbStretchPlan(
        settings_path=f"|AdvPy_{limb_label}Settings",
        global_scale_attribute=f"{limb_label.lower()}GlobalScale",
        global_scale_default=1.0,
        sides=tuple(sides),
        limb_label=limb_label,
    )


def audit_body_limb_stretch(
    plan: BodyLimbStretchPlan,
    snapshot: BodyLimbStretchSnapshot,
    *,
    tolerance: float = 1e-4,
    expected_segment_factor_sources_by_side: Mapping[
        FitBuildSide,
        tuple[str, str],
    ] | None = None,
) -> tuple[BodyLimbStretchIssue, ...]:
    label = plan.limb_label
    issues = []
    if snapshot.settings_path != plan.settings_path:
        issues.append(BodyLimbStretchIssue(
            "settings_mismatch", f"{label} stretch 设置节点不一致"
        ))
    expected_global_plug = f"{plan.settings_path}.{plan.global_scale_attribute}"
    if (
        snapshot.global_scale_plug != expected_global_plug
        or abs(snapshot.global_scale_value - plan.global_scale_default) > tolerance
    ):
        issues.append(BodyLimbStretchIssue(
            "global_scale_mismatch", f"{label} stretch 全局比例输入不一致"
        ))
    actual = {state.side: state for state in snapshot.sides}
    for spec in plan.sides:
        state = actual.get(spec.side)
        if state is None:
            issues.append(BodyLimbStretchIssue(
                "missing_side", f"缺少 {label} stretch 侧", spec.side.value
            ))
            continue
        plug = f"{plan.settings_path}.{spec.attribute}"
        expected_factor_sources = (
            expected_segment_factor_sources_by_side.get(spec.side, ())
            if expected_segment_factor_sources_by_side is not None
            else (
                f"{spec.blend_name}.outputR",
                f"{spec.blend_name}.outputR",
            )
        )
        checks = (
            (state.attribute_plug == plug and abs(state.attribute_value - 1.0) <= tolerance, "attribute_mismatch", f"{label} stretch 属性不一致"),
            (state.start_path == spec.start_path and _close(state.start_position, spec.start_position, tolerance), "start_mismatch", f"{label} stretch 起点不一致"),
            (state.distance_name == spec.distance_name and state.distance_sources == (f"{spec.start_path}.worldMatrix[0]", f"{spec.target_control_path}.worldMatrix[0]"), "distance_wiring", f"{label} stretch 测距连线不一致"),
            (state.rest_scale_name == spec.rest_scale_name and abs(state.rest_length - spec.rest_length) <= tolerance and state.global_scale_source == expected_global_plug and state.rest_scale_operation == 1, "rest_scale_wiring", f"{label} stretch 全局参考长度连线不一致"),
            (state.ratio_name == spec.ratio_name and state.ratio_distance_source == f"{spec.distance_name}.distance" and state.ratio_divisor_source == f"{spec.rest_scale_name}.outputX" and state.ratio_operation == 2, "ratio_wiring", f"{label} stretch 比例连线不一致"),
            (state.clamp_name == spec.clamp_name and state.clamp_input_source == f"{spec.ratio_name}.outputX" and abs(state.clamp_minimum - 1.0) <= tolerance and state.clamp_maximum >= 1000.0, "clamp_wiring", f"{label} stretch no-compression 连线不一致"),
            (state.blend_name == spec.blend_name and state.blend_ratio_source == f"{spec.clamp_name}.outputR" and state.blend_weight_source == plug and abs(state.blend_base_value - 1.0) <= tolerance, "blend_wiring", f"{label} stretch 强度连线不一致"),
            (state.segment_name == spec.segment_name and _close(state.base_translations, spec.base_translations, tolerance), "segment_values", f"{label} stretch 基准段长不一致"),
            (state.segment_factor_sources == expected_factor_sources, "segment_factor_wiring", f"{label} stretch 段长比例连线不一致"),
            (state.segment_destination_sources == (f"{spec.segment_name}.outputX", f"{spec.segment_name}.outputY") and state.segment_operation == 1, "segment_output_wiring", f"{label} stretch 输出目标连线不一致"),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyLimbStretchIssue(code, message, spec.side.value))
    return tuple(issues)


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
        raise BodyLimbStretchValidationError(
            "Limb stretch 距离、绑定长度和全局比例必须为正有限数值"
        )
    return float(world_distance) / (float(rest_length) * float(global_scale))


def _close(left, right, tolerance):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
