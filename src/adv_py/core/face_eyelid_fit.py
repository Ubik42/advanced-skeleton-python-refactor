"""Order a selected closed eyelid edge ring into upper and lower arcs."""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot, isfinite, sqrt


@dataclass(frozen=True, slots=True)
class EyeLidLoop:
    edge_ids: tuple[int, ...]
    upper_vertices: tuple[int, ...]
    lower_vertices: tuple[int, ...]


def eye_lid_aperture_height(
    upper: tuple[int, ...], lower: tuple[int, ...],
    positions: dict[int, tuple[float, float, float]],
) -> float:
    """Measure the vertical opening at the shared horizontal midpoint."""
    if min(len(upper), len(lower)) < 3:
        raise ValueError("眼睑上下弧缺少足够顶点")
    rows = []
    try:
        for vertices in (upper, lower):
            points = sorted((positions[index][0], positions[index][1])
                            for index in vertices)
            if any(not isfinite(value) for point in points for value in point):
                raise ValueError("眼睑弧坐标无效")
            rows.append(points)
    except KeyError as error:
        raise ValueError("眼睑弧缺少顶点坐标") from error
    left = max(row[0][0] for row in rows)
    right = min(row[-1][0] for row in rows)
    if right - left <= 1e-9:
        raise ValueError("眼睑上下弧没有共同水平跨度")
    middle = (left + right) / 2.

    def height(points: list[tuple[float, float]]) -> float:
        for first, second in zip(points, points[1:]):
            if first[0] <= middle <= second[0] and second[0] > first[0]:
                t = (middle - first[0]) / (second[0] - first[0])
                return first[1] + t * (second[1] - first[1])
        raise ValueError("眼睑弧中点无法插值")

    gap = height(rows[0]) - height(rows[1])
    if gap <= 0:
        raise ValueError("眼睑上下弧交叉，无法量取张眼高度")
    return gap


def eye_lid_blink_offsets(
    upper: tuple[int, ...], lower: tuple[int, ...],
    positions: dict[int, tuple[float, float, float]],
    *, upper_share: float = .7,
) -> dict[str, tuple[float, ...]]:
    """Return vertical displacements that meet both arcs at one closure line."""
    if not 0. < upper_share < 1. or min(len(upper), len(lower)) < 3:
        raise ValueError("眼睑闭合弧或上眼睑闭合比例无效")
    try:
        rows = {
            "upper": sorted((positions[index][0], positions[index][1])
                            for index in upper),
            "lower": sorted((positions[index][0], positions[index][1])
                            for index in lower),
        }
    except KeyError as error:
        raise ValueError("眼睑闭合弧缺少顶点坐标") from error
    if any(not all(isfinite(value) for value in row)
           for arc in rows.values() for row in arc):
        raise ValueError("眼睑闭合弧坐标无效")
    for name, arc in rows.items():
        grouped = []
        for x, y in arc:
            if grouped and x - grouped[-1][0] <= 1e-9:
                prior_x, total_y, count = grouped[-1]
                grouped[-1] = (prior_x, total_y + y, count + 1)
            else:
                grouped.append((x, y, 1))
        if len(grouped) < 2:
            raise ValueError("眼睑闭合弧缺少水平跨度")
        rows[name] = [(x, total_y / count)
                      for x, total_y, count in grouped]

    def sample(arc: str, x: float) -> float:
        points = rows[arc]
        if x <= points[0][0]:
            return points[0][1]
        if x >= points[-1][0]:
            return points[-1][1]
        for first, second in zip(points, points[1:]):
            if x <= second[0]:
                t = (x - first[0]) / (second[0] - first[0])
                return first[1] + t * (second[1] - first[1])
        raise AssertionError("眼睑闭合插值未找到区间")

    offsets = {}
    for arc, vertices in (("upper", upper), ("lower", lower)):
        values = []
        for index, vertex in enumerate(vertices):
            if index in (0, len(vertices) - 1):
                values.append(0.)
                continue
            x, current_y = positions[vertex][:2]
            upper_y = sample("upper", x)
            lower_y = sample("lower", x)
            if upper_y + 1e-6 < lower_y:
                raise ValueError("眼睑上下弧交叉，不能生成闭合线")
            meeting_y = ((1. - upper_share) * upper_y
                         + upper_share * lower_y)
            values.append(meeting_y - current_y)
        offsets[arc] = tuple(values)
    return offsets


def eye_lid_sphere_blink(point: tuple[float, float, float],
                         eye_center: tuple[float, float, float],
                         vertical_offset: float) -> tuple[float, float]:
    """Return forward movement and X roll for a lid point on the eye sphere."""
    if not all(isfinite(value) for value in (*point, *eye_center,
                                             vertical_offset)):
        raise ValueError("眼睑或眼球中心坐标无效")
    y = point[1] - eye_center[1]
    z = point[2] - eye_center[2]
    radius = hypot(y, z)
    if radius <= 1e-6 or z <= 0:
        return 0., 0.
    closed_y = y + vertical_offset
    if abs(closed_y) >= radius:
        return 0., degrees(atan2(y, z) - atan2(closed_y, z))
    closed_z = sqrt(radius * radius - closed_y * closed_y)
    return (closed_z - z,
            degrees(atan2(y, z) - atan2(closed_y, closed_z)))


def eye_lid_area_faces(
    face_edges: tuple[tuple[int, ...], ...],
    edge_faces: tuple[tuple[int, ...], ...],
    *,
    outer_edges: tuple[int, ...],
    main_edges: tuple[int, ...],
    inner_edges: tuple[int, ...],
) -> tuple[int, ...]:
    """Find the connected face band containing Main, bounded by Outer/Inner."""
    outer, main, inner = map(set, (outer_edges, main_edges, inner_edges))
    if (not outer or not main or not inner or outer & main or
            outer & inner or main & inner):
        raise ValueError("眼睑三层边环缺失或互相重叠")
    all_edges = outer | main | inner
    if any(type(index) is not int or index < 0 or index >= len(edge_faces)
           for index in all_edges):
        raise ValueError("眼睑边索引已超出 Face 网格")
    if any(not edge_faces[index] or len(edge_faces[index]) > 2
           for index in all_edges):
        raise ValueError("眼睑区域边环包含非流形边")
    seed_faces = edge_faces[min(main)]
    if len(seed_faces) != 2:
        raise ValueError("EyeLid Main 必须位于连续表面内部")
    seen = set(seed_faces)
    pending = list(seed_faces)
    barrier = outer | inner
    while pending:
        face = pending.pop()
        if face < 0 or face >= len(face_edges):
            raise ValueError("眼睑区域面索引无效")
        for edge in face_edges[face]:
            if edge in barrier:
                continue
            for neighbor in edge_faces[edge]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
    if len(seen) == len(face_edges) or not seen:
        raise ValueError("Outer／Inner 未封闭眼睑区域")
    inner_crossings = {sum(face in seen for face in edge_faces[edge])
                       for edge in inner}
    outer_crossings = {sum(face in seen for face in edge_faces[edge])
                       for edge in outer}
    # An open inner rim may connect around the outer loop elsewhere on the
    # head. In that case both sides of Outer remain reachable from Main.
    if inner_crossings != {1} or (outer_crossings != {1} and not (
            outer_crossings == {2} and
            all(len(edge_faces[edge]) == 1 for edge in inner))):
        raise ValueError("Outer／Inner 未围住同一眼睑区域")
    if any(len(edge_faces[edge]) != 2 or
           any(face not in seen for face in edge_faces[edge])
           for edge in main):
        raise ValueError("Main 不在 Outer 与 Inner 围成的区域内")
    return tuple(sorted(seen))


def order_eye_lid_loop(
    edges: tuple[tuple[int, int, int], ...],
    positions: dict[int, tuple[float, float, float]],
    *, eye_center_y: float,
    corner_vertices: tuple[int, ...] = (),
    side: str = "Right",
) -> EyeLidLoop:
    if side not in ("Right", "Left"):
        raise ValueError("眼睑侧别无效")
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

    # The inner corner is nearer the center line: greater X on the right,
    # smaller X on the left. Explicit corners keep the same direction.
    direction = 1 if side == "Right" else -1
    auto_inner = max(adjacency, key=lambda vertex: (
        direction * positions[vertex][0],
        -abs(positions[vertex][1] - eye_center_y), -vertex))
    auto_outer = min(adjacency, key=lambda vertex: (
        direction * positions[vertex][0],
        abs(positions[vertex][1] - eye_center_y), vertex))
    if len(corner_vertices) == 2:
        inner, outer = sorted(corner_vertices,
                              key=lambda vertex: direction * positions[vertex][0],
                              reverse=True)
    elif corner_vertices:
        inner, outer = corner_vertices[0], auto_outer
    else:
        inner, outer = auto_inner, auto_outer
    if (inner == outer or direction *
            (positions[inner][0] - positions[outer][0]) <= 1e-6):
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
