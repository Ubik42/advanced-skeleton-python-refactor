from __future__ import annotations

from math import cos, isclose, radians, sin
from typing import Iterable


Matrix44 = tuple[
    float, float, float, float,
    float, float, float, float,
    float, float, float, float,
    float, float, float, float,
]

IDENTITY_MATRIX: Matrix44 = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def matrix44(values: Iterable[float]) -> Matrix44:
    result = tuple(float(value) for value in values)
    if len(result) != 16:
        raise ValueError(f"世界矩阵必须包含 16 个值，实际为 {len(result)} 个")
    return result  # type: ignore[return-value]


def translation_matrix(x: float, y: float, z: float) -> Matrix44:
    """Return row-major storage for a conventional column-vector matrix."""

    return (
        1.0, 0.0, 0.0, float(x),
        0.0, 1.0, 0.0, float(y),
        0.0, 0.0, 1.0, float(z),
        0.0, 0.0, 0.0, 1.0,
    )


def rotation_y_matrix(degrees: float) -> Matrix44:
    angle = radians(degrees)
    cosine = cos(angle)
    sine = sin(angle)
    return (
        cosine, 0.0, sine, 0.0,
        0.0, 1.0, 0.0, 0.0,
        -sine, 0.0, cosine, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def rotation_z_matrix(degrees: float) -> Matrix44:
    angle = radians(degrees)
    cosine = cos(angle)
    sine = sin(angle)
    return (
        cosine, -sine, 0.0, 0.0,
        sine, cosine, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def multiply(left: Matrix44, right: Matrix44) -> Matrix44:
    left_rows = rows(left)
    right_rows = rows(right)
    return matrix44(
        sum(left_rows[row][inner] * right_rows[inner][column] for inner in range(4))
        for row in range(4)
        for column in range(4)
    )


def with_translation(matrix: Matrix44, x: float, y: float, z: float) -> Matrix44:
    values = list(matrix)
    values[3] = float(x)
    values[7] = float(y)
    values[11] = float(z)
    return matrix44(values)


def rows(matrix: Matrix44) -> tuple[tuple[float, float, float, float], ...]:
    return tuple(tuple(matrix[index:index + 4]) for index in range(0, 16, 4))


def transpose_flat(matrix: Matrix44) -> Matrix44:
    return matrix44(matrix[column * 4 + row] for row in range(4) for column in range(4))


def almost_equal(left: Matrix44, right: Matrix44, *, tolerance: float = 1e-5) -> bool:
    return all(isclose(a, b, abs_tol=tolerance) for a, b in zip(left, right))


def translation(matrix: Matrix44) -> tuple[float, float, float]:
    return matrix[3], matrix[7], matrix[11]


def y_axis(matrix: Matrix44) -> tuple[float, float, float]:
    return matrix[1], matrix[5], matrix[9]
