"""Distribute eyelid Skin influence over the band between Outer and Inner."""
from __future__ import annotations

from collections import deque
from math import sin, pi


def _distances(adjacency: dict[int, set[int]], seeds: set[int],
               allowed: set[int]) -> dict[int, int]:
    distances = {index: 0 for index in seeds & allowed}
    pending = deque(distances)
    while pending:
        vertex = pending.popleft()
        for neighbor in adjacency.get(vertex, set()) & allowed:
            if neighbor not in distances:
                distances[neighbor] = distances[vertex] + 1
                pending.append(neighbor)
    return distances


def eyelid_skin_factors(adjacency: dict[int, set[int]],
                        positions: dict[int, tuple[float, float, float]],
                        area_vertices: set[int], boundary_vertices: set[int],
                        upper_vertices: tuple[int, ...],
                        lower_vertices: tuple[int, ...],
                        maximum: float = .85,
                        ) -> dict[int, tuple[float, float]]:
    """Return upper/lower weights for the band between Main and its boundary."""
    upper, lower = set(upper_vertices), set(lower_vertices)
    main = upper | lower
    if (not 0 < maximum <= 1 or len(upper_vertices) < 3
            or len(lower_vertices) < 3 or not main <= area_vertices
            or not boundary_vertices <= area_vertices
            or (main & boundary_vertices) - {upper_vertices[0],
                                               upper_vertices[-1]}
            or not area_vertices <= positions.keys()):
        raise ValueError("眼睑区域、边界或主环无效")
    d_main = _distances(adjacency, main, area_vertices)
    d_boundary = _distances(adjacency, boundary_vertices, area_vertices)
    d_upper = _distances(adjacency, upper, area_vertices)
    d_lower = _distances(adjacency, lower, area_vertices)
    if any(len(result) != len(area_vertices) for result in
           (d_main, d_boundary, d_upper, d_lower)):
        raise ValueError("眼睑区域存在不连通顶点")
    left_x = min(positions[index][0] for index in main)
    right_x = max(positions[index][0] for index in main)
    width = right_x - left_x
    if width <= 1e-6:
        raise ValueError("眼睑内外眼角的横向距离无效")
    result = {}
    for vertex in area_vertices:
        radial_denominator = d_main[vertex] + d_boundary[vertex]
        radial = (d_boundary[vertex] / radial_denominator
                  if radial_denominator else 0.)
        x = (positions[vertex][0] - left_x) / width
        taper = sin(pi * min(1., max(0., x)))
        arc_denominator = d_upper[vertex] + d_lower[vertex]
        upper_share = (d_lower[vertex] / arc_denominator
                       if arc_denominator else .5)
        total = maximum * radial * taper
        result[vertex] = (total * upper_share,
                          total * (1. - upper_share))
    return result


def outer_eyelid_skin_factors(adjacency: dict[int, set[int]],
                             positions: dict[int, tuple[float, float, float]],
                             inner_band_vertices: set[int],
                             upper_vertices: tuple[int, ...],
                             lower_vertices: tuple[int, ...],
                             maximum: float = .35,
                             rows: int = 2) -> dict[int, tuple[float, float]]:
    """Add a short falloff outside the Outer ring without crossing the inner band."""
    boundary = set(upper_vertices) | set(lower_vertices)
    if (not boundary or not boundary <= positions.keys()
            or not 0 < maximum <= 1 or rows < 1):
        raise ValueError("眼睑 Outer 环或衰减设置无效")
    allowed = set(positions) - (inner_band_vertices - boundary)
    distance = _distances(adjacency, boundary, allowed)
    left_x = min(positions[index][0] for index in boundary)
    right_x = max(positions[index][0] for index in boundary)
    if right_x - left_x <= 1e-6:
        raise ValueError("眼睑 Outer 环横向宽度无效")

    def nearest(vertex: int, arc: tuple[int, ...]) -> float:
        point = positions[vertex]
        return min(sum((point[axis] - positions[index][axis]) ** 2
                       for axis in range(3)) ** .5 for index in arc)

    result = {}
    for vertex, depth in distance.items():
        if depth > rows:
            continue
        x = (positions[vertex][0] - left_x) / (right_x - left_x)
        taper = sin(pi * min(1., max(0., x)))
        upper_distance = nearest(vertex, upper_vertices)
        lower_distance = nearest(vertex, lower_vertices)
        denominator = upper_distance + lower_distance
        upper_share = lower_distance / denominator if denominator else .5
        total = maximum * (rows + 1 - depth) / (rows + 1) * taper
        result[vertex] = (total * upper_share,
                          total * (1. - upper_share))
    return result


def inner_eyelid_skin_factors(adjacency: dict[int, set[int]],
                             positions: dict[int, tuple[float, float, float]],
                             area_vertices: set[int],
                             upper_vertices: tuple[int, ...],
                             lower_vertices: tuple[int, ...],
                             rows: int = 2,
                             ) -> dict[int, tuple[float, float]]:
    """Move an open eye rim and fade its influence into adjacent face rows."""
    upper = set(upper_vertices[1:-1])
    lower = set(lower_vertices[1:-1])
    rim = set(upper_vertices) | set(lower_vertices)
    if (not upper or not lower or upper & lower or rows < 1
            or not rim <= area_vertices or not area_vertices <= positions.keys()):
        raise ValueError("真实眼孔边环或衰减区域无效")
    depth = _distances(adjacency, rim, area_vertices)
    d_upper = _distances(adjacency, upper, area_vertices)
    d_lower = _distances(adjacency, lower, area_vertices)
    if any(len(row) != len(area_vertices)
           for row in (depth, d_upper, d_lower)):
        raise ValueError("真实眼孔衰减区域不连通")
    left_x = min(positions[index][0] for index in rim)
    right_x = max(positions[index][0] for index in rim)
    if right_x - left_x <= 1e-6:
        raise ValueError("真实眼孔缺少水平跨度")
    factors = {}
    for vertex, distance in depth.items():
        if distance > rows:
            continue
        x = min(1., max(0., (positions[vertex][0] - left_x)
                         / (right_x - left_x)))
        taper = min(1., 20. * min(x, 1. - x))
        if vertex in upper or vertex in lower:
            taper = 1.
        total = taper * (rows + 1 - distance) / (rows + 1)
        if vertex in upper:
            share = 1.
        elif vertex in lower:
            share = 0.
        else:
            share = d_lower[vertex] / (d_upper[vertex] + d_lower[vertex])
        factors[vertex] = (total * share, total * (1. - share))
    return factors


def split_arc_weight(x: float,
                     positions: dict[int, tuple[float, float, float]],
                     arc_vertices: tuple[int, ...],
                     mass: float) -> dict[int, float]:
    """Interpolate one vertex's weight between adjacent joints along an arc."""
    if mass < 0 or not arc_vertices or any(index not in positions
                                           for index in arc_vertices):
        raise ValueError("眼睑分段权重输入无效")
    if mass == 0:
        return {}
    ordered = sorted(arc_vertices, key=lambda index: positions[index][0])
    if x <= positions[ordered[0]][0]:
        return {ordered[0]: mass}
    for first, second in zip(ordered, ordered[1:]):
        a, b = positions[first][0], positions[second][0]
        if x <= b:
            ratio = min(1., max(0., (x - a) / (b - a))) if b > a else 0.
            return {first: mass * (1. - ratio), second: mass * ratio}
    return {ordered[-1]: mass}
