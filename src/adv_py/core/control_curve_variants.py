"""Copy a main control curve to its existing Sub or Extra layer."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .control_curves import ControlCurveValidationError


Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class ControlCurveVariantState:
    source: str
    target: str
    source_shape: str
    target_shape: str
    source_degree: int
    target_degree: int
    source_form: int
    target_form: int
    pivot: Vector3
    source_points: tuple[Vector3, ...]
    target_points: tuple[Vector3, ...]


@dataclass(frozen=True, slots=True)
class ControlCurveVariantPlan:
    variant: str
    factor: float
    before: tuple[ControlCurveVariantState, ...]
    desired: tuple[tuple[Vector3, ...], ...]


def plan_control_curve_variants(
        variant: str, before: tuple[ControlCurveVariantState, ...]
) -> ControlCurveVariantPlan:
    if variant not in ("Sub", "Extra"):
        raise ControlCurveValidationError("目标控制层只能是 Sub 或 Extra")
    if not before or len({item.target for item in before}) != len(before):
        raise ControlCurveValidationError("没有可复制的控制器层，或目标层重复")
    factor = 0.9 if variant == "Sub" else 1.1
    desired = []
    for item in before:
        if (not item.source or not item.target or item.source == item.target
                or item.source_degree != item.target_degree
                or item.source_form != item.target_form
                or len(item.source_points) != len(item.target_points)
                or not item.source_points):
            raise ControlCurveValidationError(
                "主控与目标层的曲线拓扑不一致：" + item.source)
        if any(not isfinite(value) for point in (
                item.pivot, *item.source_points, *item.target_points)
               for value in point):
            raise ControlCurveValidationError("控制曲线坐标无效：" + item.source)
        desired.append(tuple(tuple(
            item.pivot[axis] + (point[axis] - item.pivot[axis]) * factor
            for axis in range(3)) for point in item.source_points))
    return ControlCurveVariantPlan(variant, factor, before, tuple(desired))


def audit_control_curve_variants(
        plan: ControlCurveVariantPlan,
        after: tuple[ControlCurveVariantState, ...],
        *, tolerance: float = 1e-5,
) -> tuple[str, ...]:
    if len(after) != len(plan.before):
        return ("控制器层数量在复制期间改变",)
    for old, new, desired in zip(plan.before, after, plan.desired):
        if (new.source != old.source or new.target != old.target
                or new.source_shape != old.source_shape
                or new.target_shape != old.target_shape
                or new.source_degree != old.source_degree
                or new.target_degree != old.target_degree
                or new.source_form != old.source_form
                or new.target_form != old.target_form
                or new.pivot != old.pivot
                or new.source_points != old.source_points
                or len(new.target_points) != len(desired)):
            return ("主控或目标曲线在复制期间改变：" + old.source,)
        if any(abs(actual - expected) > tolerance
               for point, wanted in zip(new.target_points, desired)
               for actual, expected in zip(point, wanted)):
            return ("目标层曲线控制点写后不符：" + old.target,)
    return ()
