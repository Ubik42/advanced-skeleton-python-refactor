"""Portable snapshots and plans for post-build controller curve editing."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
import re

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


class ControlCurveColorMode(str, Enum):
    SIDE = "side"
    TYPE = "type"


@dataclass(frozen=True, slots=True)
class ControlCurveShapeColorState:
    path: str
    override_enabled: bool
    rgb_enabled: bool
    color: Vector3

    def __post_init__(self) -> None:
        if (not self.path or len(self.color) != 3
                or not all(isfinite(float(value)) and 0.0 <= float(value) <= 1.0
                           for value in self.color)):
            raise ControlCurveValidationError("控制曲线显示颜色无效")


@dataclass(frozen=True, slots=True)
class ControlCurveColorState:
    control: str
    semantic_keys: tuple[str, ...]
    shapes: tuple[ControlCurveShapeColorState, ...]

    def __post_init__(self) -> None:
        if (not self.control or not self.shapes
                or len(set(self.semantic_keys)) != len(self.semantic_keys)
                or len({shape.path for shape in self.shapes}) != len(self.shapes)):
            raise ControlCurveValidationError("控制曲线颜色快照无效")


@dataclass(frozen=True, slots=True)
class ControlCurveColorPlan:
    mode: ControlCurveColorMode
    before: tuple[ControlCurveColorState, ...]
    after: tuple[ControlCurveColorState, ...]


@dataclass(frozen=True, slots=True)
class ControlCurveAutoScaleMetric:
    state: ControlCurveState
    semantic_keys: tuple[str, ...]
    current_world_radius: float
    surface_distance: float
    mesh_extent: Vector3
    up_axis: str

    def __post_init__(self) -> None:
        numbers = (self.current_world_radius, self.surface_distance,
                   *self.mesh_extent)
        if (self.up_axis not in "xyz" or len(self.mesh_extent) != 3
                or not all(isfinite(float(value)) and float(value) >= 0.0
                           for value in numbers)
                or self.current_world_radius <= 1e-8
                or max(self.mesh_extent) <= 1e-8):
            raise ControlCurveValidationError("控制曲线自动缩放测量无效")


@dataclass(frozen=True, slots=True)
class ControlCurveAutoScaleChange:
    control: str
    factor: float
    target_world_radius: float
    before: ControlCurveState
    after: ControlCurveState


@dataclass(frozen=True, slots=True)
class ControlCurveAutoScalePlan:
    mesh: str
    changes: tuple[ControlCurveAutoScaleChange, ...]


SIDE_PALETTE = {
    "left": (0.18, 0.45, 1.0),
    "right": (1.0, 0.22, 0.18),
    "center": (1.0, 0.72, 0.12),
}

TYPE_PALETTE = {
    "global": (1.0, 0.72, 0.12),
    "fk": (0.18, 0.45, 1.0),
    "ik": (0.12, 0.9, 0.42),
    "pole": (0.72, 0.24, 1.0),
    "settings": (1.0, 0.38, 0.12),
    "body": (0.2, 0.82, 0.9),
}


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in re.split(r"[._|:]+", value) if token)


def control_curve_side(state: ControlCurveColorState) -> str:
    tokens = _tokens(state.control)
    semantic = tuple(token for key in state.semantic_keys for token in _tokens(key))
    values = tokens + semantic
    if "l" in values or "left" in values:
        return "left"
    if "r" in values or "right" in values:
        return "right"
    return "center"


def control_curve_type(state: ControlCurveColorState) -> str:
    keys = tuple(key.lower() for key in state.semantic_keys)
    tokens = tuple(token for key in keys for token in _tokens(key))
    path_tokens = _tokens(state.control)
    if any(key == "global" or key.startswith("global.") for key in keys):
        return "global"
    if "pole" in tokens or "pv" in path_tokens:
        return "pole"
    if "ik" in tokens:
        return "ik"
    if "fk" in tokens:
        return "fk"
    if "settings" in tokens or "settings" in path_tokens:
        return "settings"
    return "body"


def plan_control_curve_colors(
    controls: tuple[ControlCurveColorState, ...],
    mode: ControlCurveColorMode | str,
) -> ControlCurveColorPlan:
    try:
        resolved_mode = ControlCurveColorMode(mode)
    except (TypeError, ValueError) as exc:
        raise ControlCurveValidationError("控制曲线颜色模式必须是 side 或 type") from exc
    if not controls or len({state.control for state in controls}) != len(controls):
        raise ControlCurveValidationError("至少需要一个且不能重复的控制曲线")
    palette = SIDE_PALETTE if resolved_mode is ControlCurveColorMode.SIDE else TYPE_PALETTE
    classifier = control_curve_side if resolved_mode is ControlCurveColorMode.SIDE else control_curve_type
    after = tuple(ControlCurveColorState(
        state.control,
        state.semantic_keys,
        tuple(ControlCurveShapeColorState(shape.path, True, True,
                                          palette[classifier(state)])
              for shape in state.shapes),
    ) for state in controls)
    return ControlCurveColorPlan(resolved_mode, controls, after)


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


def plan_control_curve_auto_scale(
    mesh: str, metrics: tuple[ControlCurveAutoScaleMetric, ...]
) -> ControlCurveAutoScalePlan:
    if not mesh or not metrics or len({row.state.control for row in metrics}) != len(metrics):
        raise ControlCurveValidationError("自动缩放需要网格和不重复的控制器测量")
    changes = []
    for row in metrics:
        diagonal = sum(value * value for value in row.mesh_extent) ** 0.5
        keys = tuple(key.lower() for key in row.semantic_keys)
        if any(key == "global" or key.startswith("global.") for key in keys):
            horizontal = tuple(value for axis, value in zip("xyz", row.mesh_extent)
                               if axis != row.up_axis)
            target = max(horizontal) * 0.6
        else:
            target = min(max(row.surface_distance * 1.15, diagonal * 0.015),
                         diagonal * 0.18)
        factor = min(max(target / row.current_world_radius, 0.05), 20.0)
        after = plan_control_curve_scale((row.state,), factor).after[0]
        changes.append(ControlCurveAutoScaleChange(
            row.state.control, factor, row.current_world_radius * factor,
            row.state, after))
    return ControlCurveAutoScalePlan(mesh, tuple(changes))
