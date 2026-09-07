from __future__ import annotations

from math import isfinite, sqrt


Vector3 = tuple[float, float, float]


class BodyLimbIkValidationError(ValueError):
    pass


def solve_limb_pole_position(
    start: Vector3,
    middle: Vector3,
    end: Vector3,
    fallback_axis: Vector3,
    *,
    limb_label: str,
    distance_scale: float = 0.75,
) -> Vector3:
    vectors = (start, middle, end, fallback_axis)
    if any(
        len(vector) != 3
        or any(isinstance(value, bool) or not isfinite(float(value)) for value in vector)
        for vector in vectors
    ):
        raise BodyLimbIkValidationError(
            f"{limb_label} IK Pole Vector 输入必须是有限三维向量"
        )
    if (
        not limb_label.isalpha()
        or isinstance(distance_scale, bool)
        or not isinstance(distance_scale, (int, float))
        or not isfinite(float(distance_scale))
        or distance_scale <= 0
    ):
        raise BodyLimbIkValidationError(
            f"{limb_label} IK Pole Vector 距离比例必须是正有限数值"
        )

    line = _subtract(end, start)
    length2 = _dot(line, line)
    if length2 <= 1e-10:
        raise BodyLimbIkValidationError(
            f"{limb_label} IK 起止关节不能重合"
        )
    projection = _add(
        start,
        _scale(line, _dot(_subtract(middle, start), line) / length2),
    )
    bend = _subtract(middle, projection)
    bend_length = sqrt(_dot(bend, bend))
    if bend_length <= 1e-6:
        fallback_projection = _scale(
            line,
            _dot(fallback_axis, line) / length2,
        )
        bend = _subtract(fallback_axis, fallback_projection)
        bend_length = sqrt(_dot(bend, bend))
    if bend_length <= 1e-10:
        raise BodyLimbIkValidationError(
            f"直{limb_label}匹配缺少垂直于关节链的 Pole Vector 备用方向"
        )
    total = _length(_subtract(middle, start)) + _length(_subtract(end, middle))
    return _add(
        middle,
        _scale(bend, total * float(distance_scale) / bend_length),
    )


def _add(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a + b for a, b in zip(left, right))


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right))


def _scale(vector: Vector3, value: float) -> Vector3:
    return tuple(component * value for component in vector)


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right))


def _length(vector: Vector3) -> float:
    return sqrt(_dot(vector, vector))
