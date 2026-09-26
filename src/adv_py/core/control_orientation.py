"""Portable controller-axis planning for post-build orientation edits."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite, sqrt
import re


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
    curve_unaffected: bool = False
    mirror: bool = False
    mirrored_behavior: bool = False

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
    curve_unaffected: bool
    mirror: bool
    mirrored_behavior: bool
    changes: tuple[ControlOrientationChange, ...]


@dataclass(frozen=True, slots=True)
class CustomOrientationPreview:
    control: str
    original_matrix: tuple[float, ...]
    preview_matrix: tuple[float, ...]


def plan_custom_control_orientations(
    states: tuple[ControlOrientationState, ...],
    previews: tuple[CustomOrientationPreview, ...],
) -> tuple[ControlOrientationChange, ...]:
    """Translate manually rotated proxies into stable registered controls."""
    by_control = {state.control: state for state in states}
    if (not by_control or len(by_control) != len(states)
            or len(previews) != len(states)
            or {preview.control for preview in previews} != set(by_control)):
        raise ControlOrientationValidationError("手工方向预览与登记控制器不一致")
    changes = []
    for preview in previews:
        state = by_control[preview.control]
        if (len(preview.original_matrix) != 16
                or len(preview.preview_matrix) != 16
                or any(abs(a - b) > 1e-5 for a, b in
                       zip(state.world_matrix, preview.original_matrix))):
            raise ControlOrientationValidationError(
                f"手工方向预览期间原控制器已变化：{state.control}")
        if any(abs(a - b) > 1e-5 for a, b in zip(
                preview.preview_matrix[12:15], state.world_matrix[12:15])):
            raise ControlOrientationValidationError(
                f"手工方向仅允许旋转，不允许移动：{state.control}")
        for row in range(3):
            old_length = _normal(state.world_matrix[row * 4:row * 4 + 3])[1]
            new_length = _normal(preview.preview_matrix[row * 4:row * 4 + 3])[1]
            if abs(old_length - new_length) > 1e-5:
                raise ControlOrientationValidationError(
                    f"手工方向仅允许旋转，不允许缩放：{state.control}")
        changes.append(ControlOrientationChange(state, ControlOrientationState(
            state.control, preview.preview_matrix, state.primary_axis,
            state.secondary_axis, state.curve_unaffected, state.mirror,
            state.mirrored_behavior)))
    return tuple(changes)


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


def _opposite_semantic_axes(matrix, primary, secondary):
    """Reverse aim and up together while keeping a right-handed frame."""
    rows = list(matrix)
    for axis in (primary, secondary):
        index, _ = _axis(axis)
        for column in range(3):
            offset = index * 4 + column
            rows[offset] = -rows[offset]
    return tuple(rows)


def _is_left_control(control):
    return bool(re.search(r"_L(?=(?:FK|IK|PV)?$)",
                          control.rsplit("|", 1)[-1]))


def plan_control_orientation_axis(
    states: tuple[ControlOrientationState, ...],
    primary_axis: ControlAxis | str,
    secondary_axis: ControlAxis | str,
    curve_unaffected: bool = False,
    mirror: bool = False,
    mirrored_behavior: bool = False,
) -> ControlOrientationPlan:
    primary = ControlAxis(primary_axis)
    secondary = ControlAxis(secondary_axis)
    _validate_axis_pair(primary, secondary)
    if not states or len({state.control for state in states}) != len(states):
        raise ControlOrientationValidationError("至少需要一个且不能重复的控制器")
    if any(not isinstance(value, bool) for value in (
            curve_unaffected, mirror, mirrored_behavior)):
        raise ControlOrientationValidationError("控制器方向选项必须为布尔值")
    changes = []
    for state in states:
        canonical = state
        if _is_left_control(state.control) and state.mirrored_behavior:
            canonical = ControlOrientationState(
                state.control, _opposite_semantic_axes(
                    state.world_matrix, state.primary_axis, state.secondary_axis),
                state.primary_axis, state.secondary_axis,
                state.curve_unaffected, state.mirror, False)
        target = _target_matrix(canonical, primary, secondary)
        if _is_left_control(state.control) and mirrored_behavior:
            target = _opposite_semantic_axes(target, primary, secondary)
        changes.append(ControlOrientationChange(
            state, ControlOrientationState(
                state.control, target, primary, secondary,
                curve_unaffected, mirror, mirrored_behavior)))
    return ControlOrientationPlan(primary, secondary, curve_unaffected,
                                  mirror, mirrored_behavior, tuple(changes))


def plan_control_orientation_world(
    states: tuple[ControlOrientationState, ...],
    curve_unaffected: bool = False,
    mirror: bool = False,
) -> ControlOrientationPlan:
    """Align local XYZ to world XYZ while retaining position and axis lengths."""
    if not states or len({state.control for state in states}) != len(states):
        raise ControlOrientationValidationError("至少需要一个且不能重复的控制器")
    if not isinstance(curve_unaffected, bool) or not isinstance(mirror, bool):
        raise ControlOrientationValidationError("控制器方向选项必须为布尔值")
    changes = []
    for state in states:
        lengths = tuple(_normal(
            state.world_matrix[index * 4:index * 4 + 3])[1]
            for index in range(3))
        target = (lengths[0], 0., 0., 0.,
                  0., lengths[1], 0., 0.,
                  0., 0., lengths[2], 0.,
                  *state.world_matrix[12:15], 1.)
        changes.append(ControlOrientationChange(
            state, ControlOrientationState(
                state.control, target, ControlAxis.X, ControlAxis.Z,
                curve_unaffected, mirror, False)))
    return ControlOrientationPlan(
        ControlAxis.X, ControlAxis.Z, curve_unaffected, mirror, False,
        tuple(changes))


def plan_control_orientation_world_axis_match(
    states: tuple[ControlOrientationState, ...],
    source_axes: tuple[tuple[str, tuple[float, float, float]], ...],
    curve_unaffected: bool = False,
    mirror: bool = False,
) -> ControlOrientationPlan:
    """Match the dominant world component of each deform joint's local X."""
    if not states or len({state.control for state in states}) != len(states):
        raise ControlOrientationValidationError("至少需要一个且不能重复的控制器")
    if (len(source_axes) != len(states)
            or tuple(name for name, _ in source_axes)
            != tuple(state.control for state in states)):
        raise ControlOrientationValidationError("控制器与变形关节轴不一致")
    if not isinstance(curve_unaffected, bool) or not isinstance(mirror, bool):
        raise ControlOrientationValidationError("控制器方向选项必须为布尔值")
    changes = []
    for state, (_, source) in zip(states, source_axes):
        if len(source) != 3 or not all(isfinite(value) for value in source):
            raise ControlOrientationValidationError("变形关节 X 轴必须是有限三维向量")
        axis, _ = _normal(source)
        magnitudes = tuple(abs(value) for value in axis)
        dominant = next((index for index in range(3)
                         if all(magnitudes[index] > magnitudes[other]
                                for other in range(3) if other != index)), None)
        rows = [None, None, None]
        if dominant is None:
            # The MEL keeps its initial X aim and Z up when no component wins.
            rows[0], rows[2] = (1., 0., 0.), (0., 0., 1.)
        else:
            rows[dominant] = ((1. if axis[dominant] > 0. else -1.),
                              0., 0.)
            up_index = 2 if dominant == 1 else 1
            rows[up_index] = ((0., 0., 1.) if dominant == 1
                              else (0., 1., 0.))
        missing = next(index for index, row in enumerate(rows) if row is None)
        if missing == 0:
            rows[0] = _cross(rows[1], rows[2])
        elif missing == 1:
            rows[1] = _cross(rows[2], rows[0])
        else:
            rows[2] = _cross(rows[0], rows[1])
        lengths = tuple(_normal(
            state.world_matrix[index * 4:index * 4 + 3])[1]
            for index in range(3))
        values = tuple(value * lengths[index]
                       for index, row in enumerate(rows)
                       for value in (*row, 0.))
        target = (*values, *state.world_matrix[12:15], 1.)
        changes.append(ControlOrientationChange(
            state, ControlOrientationState(
                state.control, target, ControlAxis.X, ControlAxis.Z,
                curve_unaffected, mirror, False)))
    return ControlOrientationPlan(
        ControlAxis.X, ControlAxis.Z, curve_unaffected, mirror, False,
        tuple(changes))


def plan_control_orientation_world_match(
    states: tuple[ControlOrientationState, ...],
    child_positions: tuple[tuple[str, tuple[float, float, float]], ...],
    primary_axis: ControlAxis | str,
    secondary_axis: ControlAxis | str,
    world_up_axis: ControlAxis | str,
    curve_unaffected: bool = False,
    mirror: bool = False,
) -> ControlOrientationPlan:
    """Aim a local axis at the child; project world up around that aim."""
    primary = ControlAxis(primary_axis)
    secondary = ControlAxis(secondary_axis)
    up = ControlAxis(world_up_axis)
    _validate_axis_pair(primary, secondary)
    if not states or len({state.control for state in states}) != len(states):
        raise ControlOrientationValidationError("至少需要一个且不能重复的控制器")
    if (len(child_positions) != len(states)
            or tuple(name for name, _ in child_positions)
            != tuple(state.control for state in states)):
        raise ControlOrientationValidationError("控制器与子关节目标不一致")
    if not isinstance(curve_unaffected, bool) or not isinstance(mirror, bool):
        raise ControlOrientationValidationError("控制器方向选项必须为布尔值")
    up_index, up_sign = _axis(up)
    up_world = tuple(up_sign if index == up_index else 0.
                     for index in range(3))
    changes = []
    for state, (_, child) in zip(states, child_positions):
        if len(child) != 3:
            raise ControlOrientationValidationError("子关节位置必须是三维坐标")
        try:
            child = tuple(float(value) for value in child)
        except (TypeError, ValueError) as exc:
            raise ControlOrientationValidationError(
                "子关节位置必须是有限的三维坐标") from exc
        if any(not isfinite(value) for value in child):
            raise ControlOrientationValidationError(
                "子关节位置必须是有限的三维坐标")
        origin = state.world_matrix[12:15]
        direction = tuple(value - base for value, base
                          in zip(child, origin))
        if sum(value * value for value in direction) <= 1e-20:
            raise ControlOrientationValidationError(
                f"World Match 控制器与子关节位置重合：{state.control}")
        aim, _ = _normal(direction)
        dot = sum(a * b for a, b in zip(aim, up_world))
        projection = tuple(
            value - dot * direction
            for value, direction in zip(up_world, aim))
        if sum(value * value for value in projection) <= 1e-20:
            raise ControlOrientationValidationError(
                f"World Match 世界参考轴与子关节方向平行：{state.control}")
        projected, _ = _normal(projection)
        third, _ = _normal(_cross(aim, projected))
        lengths = tuple(_normal(
            state.world_matrix[index * 4:index * 4 + 3])[1]
            for index in range(3))
        reference = ControlOrientationState(
            state.control,
            (*tuple(value * lengths[0] for value in aim), 0.,
             *tuple(value * lengths[1] for value in projected), 0.,
             *tuple(value * lengths[2] for value in third), 0.,
             *origin, 1.))
        target = _target_matrix(reference, primary, secondary)
        changes.append(ControlOrientationChange(
            state, ControlOrientationState(
                state.control, target, primary, secondary,
                curve_unaffected, mirror, False)))
    return ControlOrientationPlan(primary, secondary,
                                  curve_unaffected, mirror, False,
                                  tuple(changes))
