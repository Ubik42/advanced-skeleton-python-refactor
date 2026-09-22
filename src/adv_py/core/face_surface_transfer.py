"""Transfer sparse sculpt displacement between different mesh topologies."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

from .face_shapes import FaceMeshSnapshot
from .face_target_asset import FaceTargetAsset


Point = tuple[float, float, float]
Triangle = tuple[int, int, int]


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(vector: Point) -> Point:
    length = sqrt(_dot(vector, vector))
    if length <= 1e-9:
        raise ValueError("对齐标记点重合或共线")
    return tuple(value / length for value in vector)  # type: ignore[return-value]


def _frame(points: tuple[Point, Point, Point]) -> tuple[Point, Point, Point]:
    first = _unit(_subtract(points[1], points[0]))
    normal = _unit(_cross(first, _subtract(points[2], points[0])))
    return first, _cross(normal, first), normal


@dataclass(frozen=True, slots=True)
class FaceSurfaceAlignment:
    """Three corresponding vertex pairs define a source-to-target rigid frame."""
    pairs: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    max_residual: float

    def __post_init__(self):
        if (not isinstance(self.pairs, tuple) or len(self.pairs) != 3
                or any(not isinstance(row, tuple) or len(row) != 2
                       or any(type(index) is not int or index < 0 for index in row)
                       for row in self.pairs)
                or len({row[0] for row in self.pairs}) != 3
                or len({row[1] for row in self.pairs}) != 3
                or isinstance(self.max_residual, bool)
                or not isinstance(self.max_residual, (float, int))
                or not isfinite(self.max_residual) or self.max_residual < 0.):
            raise ValueError("刚体对齐需要三个不重复的顶点对应和有效误差上限")

    def frames(self, source: FaceMeshSnapshot, destination: FaceMeshSnapshot
               ) -> tuple[Point, Point, tuple[Point, Point, Point],
                          tuple[Point, Point, Point]]:
        if any(s >= source.vertex_count or t >= destination.vertex_count
               for s, t in self.pairs):
            raise ValueError("刚体对齐顶点索引越界")
        source_points = tuple(source.points[s] for s, _ in self.pairs)
        target_points = tuple(destination.points[t] for _, t in self.pairs)
        source_frame = _frame(source_points)  # type: ignore[arg-type]
        target_frame = _frame(target_points)  # type: ignore[arg-type]
        for source_point, target_point in zip(source_points, target_points):
            projected = _map(source_point, source_points[0], target_points[0],
                             source_frame, target_frame)
            if sqrt(_distance_squared(projected, target_point)) > self.max_residual + 1e-9:
                raise ValueError("刚体对齐标记点误差超过上限；检查顶点对应或网格尺度")
        return source_points[0], target_points[0], source_frame, target_frame


def _rotate(vector: Point, origin_frame: tuple[Point, Point, Point],
            destination_frame: tuple[Point, Point, Point]) -> Point:
    coordinates = tuple(_dot(vector, axis) for axis in origin_frame)
    return tuple(sum(coordinates[i] * destination_frame[i][axis]
                     for i in range(3)) for axis in range(3))  # type: ignore[return-value]


def _map(point: Point, origin: Point, destination: Point,
         origin_frame: tuple[Point, Point, Point],
         destination_frame: tuple[Point, Point, Point]) -> Point:
    rotated = _rotate(_subtract(point, origin), origin_frame, destination_frame)
    return tuple(destination[i] + rotated[i] for i in range(3))  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class FaceSurfaceTransferResult:
    asset: FaceTargetAsset
    source_triangle_count: int
    transferred_vertex_count: int
    max_neutral_distance: float


@dataclass(frozen=True, slots=True)
class MeshSurfaceProjection:
    triangle_index: int
    barycentric: tuple[float, float, float]
    distance: float


@dataclass(frozen=True, slots=True)
class MeshSurfaceProjectionResult:
    rows: tuple[MeshSurfaceProjection, ...]
    max_distance: float


@dataclass(slots=True)
class _Node:
    minimum: Point
    maximum: Point
    indices: tuple[int, ...]
    left: _Node | None = None
    right: _Node | None = None


def _subtract(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Point, b: Point) -> float:
    return sum(x * y for x, y in zip(a, b))


def _distance_squared(a: Point, b: Point) -> float:
    return _dot(_subtract(a, b), _subtract(a, b))


def _aabb_distance_squared(point: Point, minimum: Point, maximum: Point) -> float:
    return sum((lo - value) ** 2 if value < lo else
               (value - hi) ** 2 if value > hi else 0.
               for value, lo, hi in zip(point, minimum, maximum))


def _closest_weights(point: Point, a: Point, b: Point,
                     c: Point) -> tuple[float, float, float]:
    ab, ac, ap = _subtract(b, a), _subtract(c, a), _subtract(point, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0. and d2 <= 0.:
        return (1., 0., 0.)
    bp = _subtract(point, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0. and d4 <= d3:
        return (0., 1., 0.)
    vc = d1 * d4 - d3 * d2
    if vc <= 0. and d1 >= 0. and d3 <= 0.:
        v = d1 / (d1 - d3)
        return (1. - v, v, 0.)
    cp = _subtract(point, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0. and d5 <= d6:
        return (0., 0., 1.)
    vb = d5 * d2 - d1 * d6
    if vb <= 0. and d2 >= 0. and d6 <= 0.:
        w = d2 / (d2 - d6)
        return (1. - w, 0., w)
    va = d3 * d6 - d5 * d4
    if va <= 0. and d4 - d3 >= 0. and d5 - d6 >= 0.:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return (0., 1. - w, w)
    denominator = va + vb + vc
    v, w = vb / denominator, vc / denominator
    return (1. - v - w, v, w)


def _weighted(points: tuple[Point, Point, Point],
              weights: tuple[float, float, float]) -> Point:
    return tuple(sum(weight * point[axis] for weight, point in zip(weights, points))
                 for axis in range(3))  # type: ignore[return-value]


def _bounds(points: tuple[Point, ...], triangles: tuple[Triangle, ...]
            ) -> tuple[tuple[Point, Point], ...]:
    result = []
    for triangle in triangles:
        vertices = tuple(points[index] for index in triangle)
        minimum = tuple(min(point[axis] for point in vertices) for axis in range(3))
        maximum = tuple(max(point[axis] for point in vertices) for axis in range(3))
        result.append((minimum, maximum))
    return tuple(result)  # type: ignore[return-value]


def _build(indices: tuple[int, ...], bounds: tuple[tuple[Point, Point], ...]) -> _Node:
    minimum = tuple(min(bounds[index][0][axis] for index in indices)
                    for axis in range(3))
    maximum = tuple(max(bounds[index][1][axis] for index in indices)
                    for axis in range(3))
    if len(indices) <= 8:
        return _Node(minimum, maximum, indices)  # type: ignore[arg-type]
    axis = max(range(3), key=lambda value: maximum[value] - minimum[value])
    ordered = tuple(sorted(indices, key=lambda index:
        (bounds[index][0][axis] + bounds[index][1][axis], index)))
    middle = len(ordered) // 2
    return _Node(minimum, maximum, (), _build(ordered[:middle], bounds),
                 _build(ordered[middle:], bounds))  # type: ignore[arg-type]


def _closest(point: Point, node: _Node, points: tuple[Point, ...],
             triangles: tuple[Triangle, ...]
             ) -> tuple[float, int, tuple[float, float, float]]:
    best = (float("inf"), -1, (0., 0., 0.))
    pending = [node]
    while pending:
        current = pending.pop()
        if _aabb_distance_squared(point, current.minimum,
                                  current.maximum) > best[0]:
            continue
        if current.indices:
            for index in current.indices:
                vertices = tuple(points[item] for item in triangles[index])
                weights = _closest_weights(point, *vertices)
                projected = _weighted(vertices, weights)
                distance = _distance_squared(point, projected)
                if distance < best[0] or (distance == best[0] and index < best[1]):
                    best = (distance, index, weights)
            continue
        children = (current.left, current.right)
        ordered = sorted((child for child in children if child is not None),
            key=lambda child: _aabb_distance_squared(point, child.minimum,
                                                       child.maximum), reverse=True)
        pending.extend(ordered)
    return best


def transfer_face_target_asset(source: FaceMeshSnapshot,
                               destination: FaceMeshSnapshot,
                               triangles: tuple[Triangle, ...],
                               asset: FaceTargetAsset, *,
                               max_distance: float,
                               alignment: FaceSurfaceAlignment | None = None
                               ) -> FaceSurfaceTransferResult:
    """Project each target vertex onto the source surface and interpolate deltas."""
    asset.points_for(source)
    projection = project_mesh_surface(source, destination, triangles,
        max_distance=max_distance, alignment=alignment)
    frames = alignment.frames(source, destination) if alignment else None
    sparse = {row[0]: row[1:] for row in asset.deltas}
    deltas = []
    for index, row in enumerate(projection.rows):
        source_delta = tuple(sparse.get(vertex, (0., 0., 0.))
                             for vertex in triangles[row.triangle_index])
        displacement = _weighted(source_delta, row.barycentric)
        if frames:
            displacement = _rotate(displacement, frames[2], frames[3])
        if max(abs(value) for value in displacement) > 1e-7:
            deltas.append((index, *displacement))
    if not deltas:
        raise ValueError("跨拓扑转移后没有有效雕刻位移")
    result = FaceTargetAsset(asset.name, asset.kind, destination.vertex_count,
        destination.topology_digest, destination.position_digest, tuple(deltas))
    return FaceSurfaceTransferResult(result, len(triangles), len(deltas),
                                     projection.max_distance)


def project_mesh_surface(source: FaceMeshSnapshot,
                         destination: FaceMeshSnapshot,
                         triangles: tuple[Triangle, ...], *,
                         max_distance: float,
                         alignment: FaceSurfaceAlignment | None = None
                         ) -> MeshSurfaceProjectionResult:
    """Map each destination vertex to its nearest source triangle."""
    if not isinstance(source, FaceMeshSnapshot):
        raise ValueError("跨拓扑转移的源网格无效")
    if (not isinstance(destination, FaceMeshSnapshot)
            or not isinstance(triangles, tuple) or not triangles
            or len(triangles) > 2_000_000
            or isinstance(max_distance, bool)
            or not isinstance(max_distance, (int, float))
            or not isfinite(max_distance) or max_distance < 0.):
        raise ValueError("跨拓扑转移的目标网格、三角面或最大距离无效")
    for row in triangles:
        if (not isinstance(row, tuple) or len(row) != 3
                or len(set(row)) != 3
                or any(type(index) is not int or not 0 <= index < source.vertex_count
                       for index in row)):
            raise ValueError("源网格三角面顶点索引无效")
        a, b, c = (source.points[index] for index in row)
        ab, ac = _subtract(b, a), _subtract(c, a)
        cross = (ab[1] * ac[2] - ab[2] * ac[1],
                 ab[2] * ac[0] - ab[0] * ac[2],
                 ab[0] * ac[1] - ab[1] * ac[0])
        if _dot(cross, cross) <= 1e-24:
            raise ValueError("源网格存在退化三角面，无法可靠转移")
    bounds = _bounds(source.points, triangles)
    tree = _build(tuple(range(len(triangles))), bounds)
    frames = alignment.frames(source, destination) if alignment else None
    rows = []
    greatest = 0.
    threshold = float(max_distance) ** 2
    for index, point in enumerate(destination.points):
        source_point = (_map(point, frames[1], frames[0], frames[3], frames[2])
                        if frames else point)
        distance, triangle_index, weights = _closest(source_point, tree,
            source.points, triangles)
        if distance > threshold + 1e-12:
            raise ValueError(f"目标顶点 {index} 距源表面超过最大允许距离")
        greatest = max(greatest, distance)
        rows.append(MeshSurfaceProjection(triangle_index, weights,
                                          sqrt(distance)))
    return MeshSurfaceProjectionResult(tuple(rows), sqrt(greatest))
