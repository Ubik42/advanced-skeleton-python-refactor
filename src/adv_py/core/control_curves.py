"""Portable snapshots and plans for post-build controller curve editing."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

Vector3 = tuple[float, float, float]


class ControlCurveValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ControlCurveShapeState:
    path: str
    degree: int
    form: int
    points: tuple[Vector3, ...]

    def __post_init__(self) -> None:
        if not self.path or self.degree < 1 or self.form not in (0, 1, 2):
            raise ControlCurveValidationError("控制曲线形状描述无效")
        if len(self.points) < 2 or any(
                len(point) != 3 or not all(isfinite(float(value)) for value in point)
                for point in self.points):
            raise ControlCurveValidationError("控制曲线 CV 必须是有限三维坐标")


@dataclass(frozen=True, slots=True)
class ControlCurveState:
    control: str
    world_matrix: tuple[float, ...]
    shapes: tuple[ControlCurveShapeState, ...]

    def __post_init__(self) -> None:
        if (not self.control or len(self.world_matrix) != 16
                or not all(isfinite(float(value)) for value in self.world_matrix)
                or not self.shapes
                or len({shape.path for shape in self.shapes}) != len(self.shapes)):
            raise ControlCurveValidationError("控制器曲线快照无效")


@dataclass(frozen=True, slots=True)
class ControlCurveScalePlan:
    factor: float
    before: tuple[ControlCurveState, ...]
    after: tuple[ControlCurveState, ...]


def plan_control_curve_scale(
    controls: tuple[ControlCurveState, ...], factor: float
) -> ControlCurveScalePlan:
    if (isinstance(factor, bool) or not isinstance(factor, (int, float))
            or not isfinite(float(factor)) or not 0.01 <= float(factor) <= 100.0):
        raise ControlCurveValidationError("控制曲线缩放倍率必须位于 0.01 到 100")
    if not controls or len({state.control for state in controls}) != len(controls):
        raise ControlCurveValidationError("至少需要一个且不能重复的控制曲线")
    value = float(factor)
    after = tuple(ControlCurveState(
        state.control,
        state.world_matrix,
        tuple(ControlCurveShapeState(
            shape.path, shape.degree, shape.form,
            tuple(tuple(component * value for component in point)
                  for point in shape.points))
              for shape in state.shapes))
        for state in controls)
    return ControlCurveScalePlan(value, controls, after)
