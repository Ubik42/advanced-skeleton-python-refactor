from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_leg_stretch import BodyLegStretchPlan
from .fit_symmetry import FitBuildSide


class BodyLegStretchBiasValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyLegStretchBiasSideSpec:
    side: FitBuildSide
    attribute: str
    default_value: float
    ratio_source: str
    segment_name: str
    original_factor_source: str
    delta_name: str
    candidates_name: str
    weights_name: str
    factors_name: str
    candidate_multipliers: tuple[float, float]
    factor_destinations: tuple[str, str]

    @property
    def factor_sources(self) -> tuple[str, str]:
        return (
            f"{self.factors_name}.output2Dx",
            f"{self.factors_name}.output2Dy",
        )


@dataclass(frozen=True, slots=True)
class BodyLegStretchBiasPlan:
    settings_path: str
    sides: tuple[BodyLegStretchBiasSideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLegStretchBiasSideState:
    side: FitBuildSide
    attribute_plug: str
    attribute_value: float
    delta_name: str
    delta_ratio_source: str | None
    delta_base_value: float
    delta_operation: int
    candidates_name: str
    candidate_sources: tuple[str | None, str | None]
    candidate_multipliers: tuple[float, float]
    candidate_operation: int
    weights_name: str
    upper_candidate_source: str | None
    upper_zero: float
    lower_zero: float
    lower_candidate_source: str | None
    bias_source: str | None
    factors_name: str
    base_factors: tuple[float, float]
    weighted_sources: tuple[str | None, str | None]
    factor_operation: int
    factor_destinations: tuple[str, str]
    factor_destination_sources: tuple[str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyLegStretchBiasSnapshot:
    settings_path: str
    sides: tuple[BodyLegStretchBiasSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyLegStretchBiasIssue:
    code: str
    message: str
    subject: str | None = None


def biased_stretch_factors(
    base_lengths: tuple[float, float],
    effective_ratio: float,
    upper_extra_share: float,
) -> tuple[float, float]:
    if (
        not isinstance(base_lengths, tuple)
        or len(base_lengths) != 2
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or value == 0.0
            for value in base_lengths
        )
        or isinstance(effective_ratio, bool)
        or not isinstance(effective_ratio, (int, float))
        or not isfinite(float(effective_ratio))
        or effective_ratio < 1.0
        or isinstance(upper_extra_share, bool)
        or not isinstance(upper_extra_share, (int, float))
        or not isfinite(float(upper_extra_share))
        or not 0.0 <= upper_extra_share <= 1.0
    ):
        raise BodyLegStretchBiasValidationError(
            "Leg stretch bias 段长、比例或分配值无效"
        )
    upper, lower = (abs(float(value)) for value in base_lengths)
    rest_length = upper + lower
    extra_ratio = float(effective_ratio) - 1.0
    share = float(upper_extra_share)
    return (
        1.0 + extra_ratio * rest_length * share / upper,
        1.0 + extra_ratio * rest_length * (1.0 - share) / lower,
    )


def plan_body_leg_stretch_bias(
    stretch: BodyLegStretchPlan,
) -> BodyLegStretchBiasPlan:
    if stretch.limb_label != "Leg":
        raise BodyLegStretchBiasValidationError(
            "Leg stretch bias 只接受 Leg stretch 计划"
        )
    sides = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        matches = tuple(spec for spec in stretch.sides if spec.side is side)
        if len(matches) != 1:
            raise BodyLegStretchBiasValidationError(
                "Leg stretch bias 要求左右各有唯一 stretch 输出"
            )
        stretch_side = matches[0]
        absolute_lengths = tuple(
            abs(float(value)) for value in stretch_side.base_translations
        )
        if (
            len(absolute_lengths) != 2
            or any(
                not isfinite(value) or value <= 1e-6
                for value in absolute_lengths
            )
            or abs(sum(absolute_lengths) - stretch_side.rest_length) > 1e-4
        ):
            raise BodyLegStretchBiasValidationError(
                "Leg stretch bias 要求两个有效且与绑定总长一致的段"
            )
        default_value = absolute_lengths[0] / stretch_side.rest_length
        prefix = f"AdvPy_LegStretchBias"
        sides.append(BodyLegStretchBiasSideSpec(
            side=side,
            attribute=f"legStretchBias_{suffix}",
            default_value=default_value,
            ratio_source=f"{stretch_side.blend_name}.outputR",
            segment_name=stretch_side.segment_name,
            original_factor_source=f"{stretch_side.blend_name}.outputR",
            delta_name=f"{prefix}Delta_{suffix}",
            candidates_name=f"{prefix}Candidates_{suffix}",
            weights_name=f"{prefix}Weights_{suffix}",
            factors_name=f"{prefix}Factors_{suffix}",
            candidate_multipliers=(
                stretch_side.rest_length / absolute_lengths[0],
                stretch_side.rest_length / absolute_lengths[1],
            ),
            factor_destinations=(
                f"{stretch_side.segment_name}.input2X",
                f"{stretch_side.segment_name}.input2Y",
            ),
        ))
    return BodyLegStretchBiasPlan(stretch.settings_path, tuple(sides))


def audit_body_leg_stretch_bias(
    plan: BodyLegStretchBiasPlan,
    snapshot: BodyLegStretchBiasSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyLegStretchBiasIssue, ...]:
    issues = []
    if snapshot.settings_path != plan.settings_path:
        issues.append(BodyLegStretchBiasIssue(
            "settings_mismatch",
            "Leg stretch bias 设置节点不一致",
        ))
    actual = {state.side: state for state in snapshot.sides}
    if set(actual) != {spec.side for spec in plan.sides}:
        issues.append(BodyLegStretchBiasIssue(
            "side_set_mismatch",
            "Leg stretch bias 侧集合不一致",
        ))
    for spec in plan.sides:
        state = actual.get(spec.side)
        if state is None:
            continue
        plug = f"{plan.settings_path}.{spec.attribute}"
        checks = (
            (
                state.attribute_plug == plug
                and abs(state.attribute_value - spec.default_value) <= tolerance,
                "attribute_mismatch",
                "Leg stretch bias 属性不一致",
            ),
            (
                state.delta_name == spec.delta_name
                and state.delta_ratio_source == spec.ratio_source
                and abs(state.delta_base_value - 1.0) <= tolerance
                and state.delta_operation == 2,
                "delta_mismatch",
                "Leg stretch bias 增量比例网络不一致",
            ),
            (
                state.candidates_name == spec.candidates_name
                and state.candidate_sources
                == (
                    f"{spec.delta_name}.output1D",
                    f"{spec.delta_name}.output1D",
                )
                and _close(
                    state.candidate_multipliers,
                    spec.candidate_multipliers,
                    tolerance,
                )
                and state.candidate_operation == 1,
                "candidate_mismatch",
                "Leg stretch bias 候选段比例网络不一致",
            ),
            (
                state.weights_name == spec.weights_name
                and state.upper_candidate_source
                == f"{spec.candidates_name}.outputX"
                and abs(state.upper_zero) <= tolerance
                and abs(state.lower_zero) <= tolerance
                and state.lower_candidate_source
                == f"{spec.candidates_name}.outputY"
                and state.bias_source == plug,
                "weight_mismatch",
                "Leg stretch bias 分配权重网络不一致",
            ),
            (
                state.factors_name == spec.factors_name
                and _close(state.base_factors, (1.0, 1.0), tolerance)
                and state.weighted_sources
                == (
                    f"{spec.weights_name}.outputR",
                    f"{spec.weights_name}.outputG",
                )
                and state.factor_operation == 1,
                "factor_mismatch",
                "Leg stretch bias 最终比例网络不一致",
            ),
            (
                state.factor_destinations == spec.factor_destinations
                and state.factor_destination_sources == spec.factor_sources,
                "destination_mismatch",
                "Leg stretch bias 输出目标不一致",
            ),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyLegStretchBiasIssue(
                    code,
                    message,
                    spec.side.value,
                ))
    return tuple(issues)


def _close(left, right, tolerance):
    return len(left) == len(right) and all(
        abs(a - b) <= tolerance for a, b in zip(left, right)
    )
