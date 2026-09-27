"""Order a selected closed eyelid edge ring into upper and lower arcs."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class EyeLidLoop:
    edge_ids: tuple[int, ...]
    upper_vertices: tuple[int, ...]
    lower_vertices: tuple[int, ...]


def order_eye_lid_loop(
    edges: tuple[tuple[int, int, int], ...],
    positions: dict[int, tuple[float, float, float]],
    *, eye_center_y: float,
    corner_vertices: tuple[int, ...] = (),
) -> EyeLidLoop:
    if len(edges) < 6 or len({row[0] for row in edges}) != len(edges):
        raise ValueError("眼睑需要至少六条互不重复的闭合边")
    adjacency: dict[int, list[int]] = {}
    pairs = set()
    for edge_id, first, second in edges:
        if (any(type(value) is not int or value < 0
                for value in (edge_id, first, second)) or first == second):
            raise ValueError("眼睑边拓扑无效")
        pair = tuple(sorted((first, second)))
        if pair in pairs:
            raise ValueError("眼睑边包含重复连接")
        pairs.add(pair)
        adjacency.setdefault(first, []).append(second)
        adjacency.setdefault(second, []).append(first)
    if (len(adjacency) != len(edges)
            or any(len(neighbors) != 2 for neighbors in adjacency.values())):
        raise ValueError("眼睑边必须构成单个无分叉闭环")
    if (set(adjacency) != set(positions)
            or not isfinite(eye_center_y)
            or any(len(point) != 3 or not all(isfinite(value) for value in point)
                   for point in positions.values())):
        raise ValueError("眼睑边缺少有效的世界顶点坐标")

    if (len(corner_vertices) > 2 or len(set(corner_vertices)) != len(corner_vertices)
            or any(vertex not in adjacency for vertex in corner_vertices)):
        raise ValueError("手选眼角须是边环上的一至两个不同顶点")

    # The original right-eye fitting starts at the vertex nearest the face
    # center line and ends at the outermost vertex. Explicit corners may
    # override that choice while retaining the right-eye X ordering.
    auto_inner = max(adjacency, key=lambda vertex: (
        positions[vertex][0], -abs(positions[vertex][1] - eye_center_y),
        -vertex))
    auto_outer = min(adjacency, key=lambda vertex: (
        positions[vertex][0], abs(positions[vertex][1] - eye_center_y),
        vertex))
    if len(corner_vertices) == 2:
        inner, outer = sorted(corner_vertices,
                              key=lambda vertex: positions[vertex][0],
                              reverse=True)
    elif corner_vertices:
        inner, outer = corner_vertices[0], auto_outer
    else:
        inner, outer = auto_inner, auto_outer
    if inner == outer or positions[inner][0] - positions[outer][0] <= 1e-6:
        raise ValueError("眼睑边环没有可区分的内外眼角")

    def walk(first_neighbor: int) -> tuple[int, ...]:
        path = [inner, first_neighbor]
        while path[-1] != outer:
            previous, current = path[-2:]
            following = [vertex for vertex in adjacency[current]
                         if vertex != previous]
            if len(following) != 1 or following[0] in path:
                raise ValueError("眼睑边环未能按顺序走到外眼角")
            path.append(following[0])
            if len(path) > len(adjacency):
                raise ValueError("眼睑边环遍历超出顶点数")
        return tuple(path)

    first, second = (walk(neighbor) for neighbor in adjacency[inner])
    if (min(len(first), len(second)) < 3
            or set(first[1:-1]) & set(second[1:-1])
            or set(first) | set(second) != set(adjacency)):
        raise ValueError("眼睑闭环不能拆成完整的上、下两条弧")
    first_height = sum(positions[index][1] for index in first[1:-1]) / (len(first)-2)
    second_height = sum(positions[index][1] for index in second[1:-1]) / (len(second)-2)
    if abs(first_height - second_height) <= 1e-6:
        raise ValueError("眼睑上下弧的高度无法区分")
    upper, lower = (first, second) if first_height > second_height else (second, first)
    return EyeLidLoop(tuple(sorted(row[0] for row in edges)), upper, lower)
