"""Original 6.925 FK bias distribution for Inbetween Part joints."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class InbetweenBiasCurve:
    name: str
    keys: tuple[tuple[float, float], ...]

    def value(self, bias: float) -> float:
        """Evaluate the linear remap after the control's ×0.1 conversion."""
        if not isfinite(bias):
            raise ValueError("Inbetween bias 必须是有限数值")
        x = max(-1.0, min(1.0, bias / 10.0))
        if x <= 0.0:
            left, right = self.keys[0], self.keys[1]
        else:
            left, right = self.keys[1], self.keys[2]
        amount = (x - left[0]) / (right[0] - left[0])
        return left[1] + (right[1] - left[1]) * amount


@dataclass(frozen=True, slots=True)
class InbetweenBiasPlan:
    start_body_name: str
    part_names: tuple[str, ...]
    control_plug: str
    unit_name: str
    start_curve: InbetweenBiasCurve
    mid_curve: InbetweenBiasCurve
    end_curve: InbetweenBiasCurve

    def curve_for_index(self, index: int) -> InbetweenBiasCurve:
        if not 0 <= index <= len(self.part_names):
            raise ValueError("Inbetween 权重索引越界")
        if index == 0:
            return self.start_curve
        if index == len(self.part_names):
            return self.end_curve
        return self.mid_curve


def plan_inbetween_bias(
    start_body_name: str,
    part_names: tuple[str, ...],
    control_plug: str,
) -> InbetweenBiasPlan:
    """Plan Start/Mid/End remapValue nodes used by FK Inbetween.

    In 6.925 the control bias is multiplied by 0.1. The remapValue input
    range is [-1, 1], with a middle key at 0. Start uses [0, w, 1],
    whereas Mid and End use [1/n, w, 0], where w = 1/(n+1).
    """
    count = len(part_names)
    if (count < 1 or len(set(part_names)) != count
            or not start_body_name or not control_plug):
        raise ValueError("Inbetween Bias 需要非空且唯一的 Part 链和控制通道")
    prefix = "AdvPy_" + start_body_name + "_Inbetween"
    weight = 1.0 / (count + 1)
    return InbetweenBiasPlan(
        start_body_name, part_names, control_plug,
        prefix + "BiasUnit",
        InbetweenBiasCurve(prefix + "StartBiasRemap",
                             ((-1.0, 0.0), (0.0, weight), (1.0, 1.0))),
        InbetweenBiasCurve(prefix + "MidBiasRemap",
                             ((-1.0, 1.0 / count), (0.0, weight),
                              (1.0, 0.0))),
        InbetweenBiasCurve(prefix + "EndBiasRemap",
                             ((-1.0, 1.0 / count), (0.0, weight),
                              (1.0, 0.0))),
    )
