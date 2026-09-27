"""Stable surface location across posed and build-pose mesh evaluations."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


Point = tuple[float, float, float]


def _sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


@dataclass(frozen=True, slots=True)
class SurfaceAnchor:
    vertex_indices: tuple[int, int, int]
    barycentric: tuple[float, float, float]

    def resolve(self, points: tuple[Point, ...]) -> Point:
        if (len(self.vertex_indices) != 3
                or len(self.barycentric) != 3
                or any(index < 0 or index >= len(points)
                       for index in self.vertex_indices)):
            raise ValueError("贴附三角形索引无效")
        weights = self.barycentric
        if (any(not isfinite(value) or value < -1e-8 for value in weights)
                or abs(sum(weights) - 1.0) > 1e-6):
            raise ValueError("贴附点重心权重无效")
        vertices = tuple(points[index] for index in self.vertex_indices)
        if any(not isfinite(axis) for vertex in vertices for axis in vertex):
            raise ValueError("贴附网格包含非有限坐标")
        return tuple(sum(weights[index] * vertices[index][axis]
                         for index in range(3))
                     for axis in range(3))  # type: ignore[return-value]


def _closest_barycentric(point: Point, a: Point, b: Point,
                         c: Point) -> tuple[float, float, float]:
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(point, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return 1.0, 0.0, 0.0
    bp = _sub(point, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return 0.0, 1.0, 0.0
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return 1.0 - v, v, 0.0
    cp = _sub(point, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return 0.0, 0.0, 1.0
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return 1.0 - w, 0.0, w
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return 0.0, 1.0 - w, w
    denominator = va + vb + vc
    if abs(denominator) < 1e-12:
        raise ValueError("贴附三角形退化")
    v, w = vb / denominator, vc / denominator
    return 1.0 - v - w, v, w


def anchor_on_polygon(point: Point, indices: tuple[int, ...],
                      points: tuple[Point, ...]) -> SurfaceAnchor:
    """Find the nearest triangle in one Maya polygon, preserving vertex IDs."""
    if (len(indices) < 3 or len(set(indices)) != len(indices)
            or any(index < 0 or index >= len(points) for index in indices)
            or any(not isfinite(axis) for axis in point)):
        raise ValueError("贴附多边形输入无效")
    candidates = []
    for offset in range(1, len(indices) - 1):
        triangle = indices[0], indices[offset], indices[offset + 1]
        a, b, c = (points[index] for index in triangle)
        ab, ac = _sub(b, a), _sub(c, a)
        area = (ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0])
        if _dot(area, area) < 1e-20:
            continue
        try:
            weights = _closest_barycentric(point, a, b, c)
        except ValueError:
            continue
        anchor = SurfaceAnchor(triangle, weights)
        resolved = anchor.resolve(points)
        error = sum((a - b) ** 2 for a, b in zip(point, resolved))
        candidates.append((error, offset, anchor))
    if not candidates:
        raise ValueError("贴附多边形没有非退化三角形")
    return min(candidates, key=lambda item: (item[0], item[1]))[2]
