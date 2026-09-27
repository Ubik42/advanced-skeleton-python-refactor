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
                        maximum: float = .85) -> dict[int, tuple[float, float]]:
    """Return upper/lower weights; zero on both boundaries and eye corners."""
    upper, lower = set(upper_vertices), set(lower_vertices)
    main = upper | lower
    if (not 0 < maximum <= 1 or len(upper_vertices) < 3
            or len(lower_vertices) < 3 or not main <= area_vertices
            or not boundary_vertices <= area_vertices
            or main & boundary_vertices or not area_vertices <= positions.keys()):
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
