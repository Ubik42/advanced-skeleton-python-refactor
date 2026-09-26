"""Application boundary for scaling registered control curves."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.control_curves import (
    ControlCurveScalePlan, ControlCurveState, ControlCurveValidationError,
    plan_control_curve_scale,
)


class ControlCurveHost(Protocol):
    def capture_control_curves(
        self, controls: tuple[str, ...], *, strict: bool
    ) -> tuple[ControlCurveState, ...]: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def set_control_curve_points(
        self, shape: str, points: tuple[tuple[float, float, float], ...]
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ControlCurveScaleResult:
    plan: ControlCurveScalePlan
    verified: tuple[ControlCurveState, ...]


class ScaleControlCurves:
    def __init__(self, host: ControlCurveHost) -> None:
        self._host = host

    def plan(self, controls: tuple[str, ...], factor: float, *,
             strict: bool = True) -> ControlCurveScalePlan:
        if not controls or len(set(controls)) != len(controls):
            raise ControlCurveValidationError("控制器列表不能为空或重复")
        return plan_control_curve_scale(
            self._host.capture_control_curves(controls, strict=strict), factor)

    def apply(self, controls: tuple[str, ...], factor: float, *,
              strict: bool = True) -> ControlCurveScaleResult:
        plan = self.plan(controls, factor, strict=strict)
        with self._host.transaction(
                f"缩放 {len(plan.before)} 个控制曲线，倍率 {plan.factor:g}"):
            for state in plan.after:
                for shape in state.shapes:
                    self._host.set_control_curve_points(shape.path, shape.points)
            verified = self._host.capture_control_curves(
                tuple(state.control for state in plan.after), strict=True)
            self._verify(plan, verified)
        return ControlCurveScaleResult(plan, verified)

    @staticmethod
    def _verify(plan: ControlCurveScalePlan,
                actual: tuple[ControlCurveState, ...]) -> None:
        if len(actual) != len(plan.after):
            raise RuntimeError("控制曲线缩放后复检失败：控制器数量变化")
        for expected, found in zip(plan.after, actual):
            if (found.control != expected.control
                    or any(abs(a - b) > 1e-8 for a, b in
                           zip(found.world_matrix, expected.world_matrix))
                    or len(found.shapes) != len(expected.shapes)):
                raise RuntimeError("控制曲线缩放后复检失败：控制变换或形状集合变化")
            for wanted_shape, found_shape in zip(expected.shapes, found.shapes):
                if (found_shape.path != wanted_shape.path
                        or found_shape.degree != wanted_shape.degree
                        or found_shape.form != wanted_shape.form
                        or len(found_shape.points) != len(wanted_shape.points)):
                    raise RuntimeError("控制曲线缩放后复检失败：曲线拓扑变化")
                if any(abs(a - b) > 1e-6
                       for wanted, current in zip(wanted_shape.points,
                                                  found_shape.points)
                       for a, b in zip(wanted, current)):
                    raise RuntimeError("控制曲线缩放后复检失败：CV 位置不一致")
