"""Portable controller-axis planning for post-build orientation edits."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import sqrt


class ControlOrientationValidationError(ValueError):
    pass


class ControlAxis(str, Enum):
    X = "X"
    Y = "Y"
    Z = "Z"
    NEG_X = "-X"
    NEG_Y = "-Y"
    NEG_Z = "-Z"


@dataclass(frozen=True, slots=True)
class ControlOrientationState:
    control: str
    world_matrix: tuple[float, ...]
    primary_axis: ControlAxis = ControlAxis.X
    secondary_axis: ControlAxis = ControlAxis.Y

    def __post_init__(self) -> None:
        if not self.control or len(self.world_matrix) != 16:
            raise ControlOrientationValidationError("控制器方向快照无效")
        _validate_axis_pair(self.primary_axis, self.secondary_axis)


@dataclass(frozen=True, slots=True)
class ControlOrientationChange:
    before: ControlOrientationState
    after: ControlOrientationState


@dataclass(frozen=True, slots=True)
class ControlOrientationPlan:
    primary_axis: ControlAxis
    secondary_axis: ControlAxis
    changes: tuple[ControlOrientationChange, ...]


def _axis(axis: ControlAxis | str) -> tuple[int, float]:
    try:
        value = ControlAxis(axis)
    except (TypeError, ValueError) as exc:
        raise ControlOrientationValidationError("控制器轴必须是 X/Y/Z 或其负方向") from exc
    text = value.value
    return "XYZ".index(text[-1]), -1.0 if text.startswith("-") else 1.0


def _validate_axis_pair(primary: ControlAxis | str,
                        secondary: ControlAxis | str) -> None:
    if _axis(primary)[0] == _axis(secondary)[0]:
        raise ControlOrientationValidationError("Primary 与 Secondary 不能位于同一坐标轴")


def _normal(vector):
    length = sqrt(sum(value * value for value in vector))
    if length <= 1e-10:
        raise ControlOrientationValidationError("控制器世界矩阵轴长度为零")
    return tuple(value / length for value in vector), length


def _cross(left, right):
    return (left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0])


def _semantic_vector(matrix, axis):
    index, sign = _axis(axis)
    vector, _ = _normal(matrix[index * 4:index * 4 + 3])
    return tuple(sign * value for value in vector)


def _target_matrix(state, primary, secondary):
    _validate_axis_pair(primary, secondary)
    primary_world = _semantic_vector(state.world_matrix, state.primary_axis)
    secondary_world = _semantic_vector(state.world_matrix, state.secondary_axis)
    primary_index, primary_sign = _axis(primary)
    secondary_index, secondary_sign = _axis(secondary)
    rows = [None, None, None]
    rows[primary_index] = tuple(primary_sign * value for value in primary_world)
    rows[secondary_index] = tuple(secondary_sign * value for value in secondary_world)
    missing = next(index for index, value in enumerate(rows) if value is None)
    if missing == 0:
        rows[0] = _cross(rows[1], rows[2])
    elif missing == 1:
        rows[1] = _cross(rows[2], rows[0])
    else:
        rows[2] = _cross(rows[0], rows[1])
    scales = tuple(_normal(state.world_matrix[index * 4:index * 4 + 3])[1]
                   for index in range(3))
    values = []
    for row, scale in zip(rows, scales):
        normalized, _ = _normal(row)
        values.extend(value * scale for value in normalized)
        values.append(0.0)
    values.extend(state.world_matrix[12:15])
    values.append(1.0)
    return tuple(values)


def plan_control_orientation_axis(
    states: tuple[ControlOrientationState, ...],
    primary_axis: ControlAxis | str,
    secondary_axis: ControlAxis | str,
) -> ControlOrientationPlan:
    primary = ControlAxis(primary_axis)
    secondary = ControlAxis(secondary_axis)
    _validate_axis_pair(primary, secondary)
    if not states or len({state.control for state in states}) != len(states):
        raise ControlOrientationValidationError("至少需要一个且不能重复的控制器")
    changes = tuple(ControlOrientationChange(
        state,
        ControlOrientationState(state.control, _target_matrix(
            state, primary, secondary), primary, secondary),
    ) for state in states)
    return ControlOrientationPlan(primary, secondary, changes)
