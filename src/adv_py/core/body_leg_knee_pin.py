from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_leg_ik import BodyLegIkPlan
from .body_leg_stretch import BodyLegStretchPlan
from .body_leg_stretch_bias import BodyLegStretchBiasPlan
from .fit_symmetry import FitBuildSide


class BodyLegKneePinValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyLegKneePinSideSpec:
    side: FitBuildSide
    attribute: str
    default_value: float
    start_matrix_source: str
    pole_matrix_source: str
    ankle_matrix_source: str
    global_scale_source: str
    normal_factor_sources: tuple[str, str]
    factor_destinations: tuple[str, str]
    upper_distance_name: str
    lower_distance_name: str
    local_lengths_name: str
    clamp_name: str
    pin_factors_name: str
    factors_name: str
    ratio_terms_name: str
    total_ratio_name: str
    base_lengths: tuple[float, float]
    rest_length: float
    minimum_length: float

    @property
    def node_names(self) -> tuple[str, ...]:
        return (
            self.upper_distance_name,
            self.lower_distance_name,
            self.local_lengths_name,
            self.clamp_name,
            self.pin_factors_name,
            self.factors_name,
            self.ratio_terms_name,
            self.total_ratio_name,
        )

    @property
    def factor_sources(self) -> tuple[str, str]:
        return (
            f"{self.factors_name}.outputR",
            f"{self.factors_name}.outputG",
        )

    @property
    def total_ratio_source(self) -> str:
        return f"{self.total_ratio_name}.output1D"


@dataclass(frozen=True, slots=True)
class BodyLegKneePinPlan:
    settings_path: str
    sides: tuple[BodyLegKneePinSideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLegKneePinSideState:
    side: FitBuildSide
    attribute_plug: str
    attribute_value: float
    upper_distance_name: str
    upper_matrix_sources: tuple[str | None, str | None]
    lower_distance_name: str
    lower_matrix_sources: tuple[str | None, str | None]
    local_lengths_name: str
    local_distance_sources: tuple[str | None, str | None]
    global_scale_sources: tuple[str | None, str | None]
    local_operation: int
    clamp_name: str
    clamp_sources: tuple[str | None, str | None]
    minimum_lengths: tuple[float, float]
    maximum_lengths: tuple[float, float]
    pin_factors_name: str
    pin_length_sources: tuple[str | None, str | None]
    base_divisors: tuple[float, float]
    pin_operation: int
    factors_name: str
    pin_factor_sources: tuple[str | None, str | None]
    normal_factor_sources: tuple[str | None, str | None]
    weight_source: str | None
    ratio_terms_name: str
    ratio_factor_sources: tuple[str | None, str | None]
    ratio_weights: tuple[float, float]
    ratio_operation: int
    total_ratio_name: str
    ratio_term_sources: tuple[str | None, str | None]
    total_operation: int
    factor_destinations: tuple[str, str]
    factor_destination_sources: tuple[str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyLegKneePinSnapshot:
    settings_path: str
    sides: tuple[BodyLegKneePinSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyLegKneePinIssue:
    code: str
    message: str
    subject: str | None = None


def knee_pin_factors(
    base_lengths: tuple[float, float],
    normal_factors: tuple[float, float],
    world_distances: tuple[float, float],
    global_scale: float,
    pin_weight: float,
    *,
    minimum_length: float = 1e-4,
) -> tuple[tuple[float, float], float]:
    pairs = (base_lengths, normal_factors, world_distances)
    if not all(isinstance(pair, tuple) and len(pair) == 2 for pair in pairs):
        raise BodyLegKneePinValidationError(
            "Leg knee pin 段长、距离、比例或权重无效"
        )
    values = (*base_lengths, *normal_factors, *world_distances)
    if (
        any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            for value in values
        )
        or any(abs(float(value)) <= 1e-8 for value in base_lengths)
        or any(float(value) <= 0.0 for value in normal_factors)
        or any(float(value) < 0.0 for value in world_distances)
        or isinstance(global_scale, bool)
        or not isinstance(global_scale, (int, float))
        or not isfinite(float(global_scale))
        or float(global_scale) <= 0.0
        or isinstance(pin_weight, bool)
        or not isinstance(pin_weight, (int, float))
        or not isfinite(float(pin_weight))
        or not 0.0 <= float(pin_weight) <= 1.0
        or isinstance(minimum_length, bool)
        or not isinstance(minimum_length, (int, float))
        or not isfinite(float(minimum_length))
        or float(minimum_length) <= 0.0
    ):
        raise BodyLegKneePinValidationError(
            "Leg knee pin 段长、距离、比例或权重无效"
        )

    bases = tuple(abs(float(value)) for value in base_lengths)
    normal_lengths = tuple(
        base * float(factor)
        for base, factor in zip(bases, normal_factors)
    )
    pin_lengths = tuple(
        max(float(distance) / float(global_scale), float(minimum_length))
        for distance in world_distances
    )
    weight = float(pin_weight)
    final_lengths = tuple(
        normal * (1.0 - weight) + pinned * weight
        for normal, pinned in zip(normal_lengths, pin_lengths)
    )
    factors = tuple(
        length / base for length, base in zip(final_lengths, bases)
    )
    return factors, sum(final_lengths) / sum(bases)


def plan_body_leg_knee_pin(
    stretch: BodyLegStretchPlan,
    stretch_bias: BodyLegStretchBiasPlan,
    ik: BodyLegIkPlan,
    *,
    minimum_length: float = 1e-4,
) -> BodyLegKneePinPlan:
    if (
        stretch.limb_label != "Leg"
        or stretch.settings_path != stretch_bias.settings_path
        or isinstance(minimum_length, bool)
        or not isinstance(minimum_length, (int, float))
        or not isfinite(float(minimum_length))
        or float(minimum_length) <= 0.0
    ):
        raise BodyLegKneePinValidationError(
            "Leg knee pin 输入计划或最小段长无效"
        )

    sides = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        stretch_matches = tuple(spec for spec in stretch.sides if spec.side is side)
        bias_matches = tuple(spec for spec in stretch_bias.sides if spec.side is side)
        ik_matches = tuple(spec for spec in ik.limbs if spec.side is side)
        if any(len(matches) != 1 for matches in (
            stretch_matches,
            bias_matches,
            ik_matches,
        )):
            raise BodyLegKneePinValidationError(
                "Leg knee pin 要求左右各有唯一 stretch、bias 与 IK 输入"
            )
        stretch_side = stretch_matches[0]
        bias_side = bias_matches[0]
        ik_side = ik_matches[0]
        base_lengths = tuple(
            abs(float(value)) for value in stretch_side.base_translations
        )
        expected_destinations = (
            f"{stretch_side.segment_name}.input2X",
            f"{stretch_side.segment_name}.input2Y",
        )
        if (
            len(base_lengths) != 2
            or any(not isfinite(value) or value <= 1e-8 for value in base_lengths)
            or abs(sum(base_lengths) - stretch_side.rest_length) > 1e-4
            or bias_side.factor_destinations != expected_destinations
            or ik_side.ankle_control_path != stretch_side.ankle_control_path
            or ik_side.pole_control_path == ik_side.ankle_control_path
        ):
            raise BodyLegKneePinValidationError(
                "Leg knee pin 段长、输出目标或 IK 控制定义不一致"
            )
        prefix = "AdvPy_LegKneePin"
        sides.append(BodyLegKneePinSideSpec(
            side=side,
            attribute=f"legKneePin_{suffix}",
            default_value=0.0,
            start_matrix_source=f"{stretch_side.start_path}.worldMatrix[0]",
            pole_matrix_source=f"{ik_side.pole_control_path}.worldMatrix[0]",
            ankle_matrix_source=f"{stretch_side.ankle_control_path}.worldMatrix[0]",
            global_scale_source=(
                f"{stretch.settings_path}.{stretch.global_scale_attribute}"
            ),
            normal_factor_sources=bias_side.factor_sources,
            factor_destinations=expected_destinations,
            upper_distance_name=f"{prefix}UpperDistance_{suffix}",
            lower_distance_name=f"{prefix}LowerDistance_{suffix}",
            local_lengths_name=f"{prefix}LocalLengths_{suffix}",
            clamp_name=f"{prefix}Clamp_{suffix}",
            pin_factors_name=f"{prefix}PinFactors_{suffix}",
            factors_name=f"{prefix}Factors_{suffix}",
            ratio_terms_name=f"{prefix}RatioTerms_{suffix}",
            total_ratio_name=f"{prefix}TotalRatio_{suffix}",
            base_lengths=base_lengths,
            rest_length=stretch_side.rest_length,
            minimum_length=float(minimum_length),
        ))
    return BodyLegKneePinPlan(stretch.settings_path, tuple(sides))


def audit_body_leg_knee_pin(
    plan: BodyLegKneePinPlan,
    snapshot: BodyLegKneePinSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyLegKneePinIssue, ...]:
    issues = []
    if snapshot.settings_path != plan.settings_path:
        issues.append(BodyLegKneePinIssue(
            "settings_mismatch",
            "Leg knee pin 设置节点不一致",
        ))
    actual = {state.side: state for state in snapshot.sides}
    if set(actual) != {spec.side for spec in plan.sides}:
        issues.append(BodyLegKneePinIssue(
            "side_set_mismatch",
            "Leg knee pin 侧集合不一致",
        ))
    for spec in plan.sides:
        state = actual.get(spec.side)
        if state is None:
            continue
        plug = f"{plan.settings_path}.{spec.attribute}"
        ratio_weights = tuple(value / spec.rest_length for value in spec.base_lengths)
        checks = (
            (
                state.attribute_plug == plug
                and abs(state.attribute_value - spec.default_value) <= tolerance,
                "attribute_mismatch",
                "Leg knee pin 属性不一致",
            ),
            (
                state.upper_distance_name == spec.upper_distance_name
                and state.upper_matrix_sources
                == (spec.start_matrix_source, spec.pole_matrix_source)
                and state.lower_distance_name == spec.lower_distance_name
                and state.lower_matrix_sources
                == (spec.pole_matrix_source, spec.ankle_matrix_source),
                "distance_mismatch",
                "Leg knee pin 双段测距网络不一致",
            ),
            (
                state.local_lengths_name == spec.local_lengths_name
                and state.local_distance_sources
                == (
                    f"{spec.upper_distance_name}.distance",
                    f"{spec.lower_distance_name}.distance",
                )
                and state.global_scale_sources
                == (spec.global_scale_source, spec.global_scale_source)
                and state.local_operation == 2,
                "local_length_mismatch",
                "Leg knee pin 全局比例补偿网络不一致",
            ),
            (
                state.clamp_name == spec.clamp_name
                and state.clamp_sources
                == (
                    f"{spec.local_lengths_name}.outputX",
                    f"{spec.local_lengths_name}.outputY",
                )
                and _close(
                    state.minimum_lengths,
                    (spec.minimum_length, spec.minimum_length),
                    tolerance,
                )
                and all(value >= 1000.0 for value in state.maximum_lengths),
                "clamp_mismatch",
                "Leg knee pin 最小段长保护网络不一致",
            ),
            (
                state.pin_factors_name == spec.pin_factors_name
                and state.pin_length_sources
                == (
                    f"{spec.clamp_name}.outputR",
                    f"{spec.clamp_name}.outputG",
                )
                and _close(state.base_divisors, spec.base_lengths, tolerance)
                and state.pin_operation == 2,
                "pin_factor_mismatch",
                "Leg knee pin 距离比例网络不一致",
            ),
            (
                state.factors_name == spec.factors_name
                and state.pin_factor_sources
                == (
                    f"{spec.pin_factors_name}.outputX",
                    f"{spec.pin_factors_name}.outputY",
                )
                and state.normal_factor_sources == spec.normal_factor_sources
                and state.weight_source == plug,
                "factor_mismatch",
                "Leg knee pin 混合输出网络不一致",
            ),
            (
                state.ratio_terms_name == spec.ratio_terms_name
                and state.ratio_factor_sources == spec.factor_sources
                and _close(state.ratio_weights, ratio_weights, tolerance)
                and state.ratio_operation == 1
                and state.total_ratio_name == spec.total_ratio_name
                and state.ratio_term_sources
                == (
                    f"{spec.ratio_terms_name}.outputX",
                    f"{spec.ratio_terms_name}.outputY",
                )
                and state.total_operation == 1,
                "total_ratio_mismatch",
                "Leg knee pin 最终总长度比例网络不一致",
            ),
            (
                state.factor_destinations == spec.factor_destinations
                and state.factor_destination_sources == spec.factor_sources,
                "destination_mismatch",
                "Leg knee pin 输出目标不一致",
            ),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyLegKneePinIssue(
                    code,
                    message,
                    spec.side.value,
                ))
    return tuple(issues)


def _close(left, right, tolerance):
    return len(left) == len(right) and all(
        abs(a - b) <= tolerance for a, b in zip(left, right)
    )
