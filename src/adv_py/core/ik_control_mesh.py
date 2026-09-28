"""Plan the original IK curve-to-control-mesh conversion."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt


Point = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class IKControlCurve:
    control: str
    curve: str
    global_control: str
    points: tuple[Point, ...]
    closed: bool
    override_color: int
    visibility_source: str | None


@dataclass(frozen=True, slots=True)
class IKControlMeshItem:
    control: str
    curve: str
    global_control: str
    shape_name: str
    vertices: tuple[Point, ...]
    faces: tuple[tuple[int, int, int, int], ...]
    shader: str | None
    visibility_source: str | None


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(v: Point) -> Point | None:
    length = sqrt(sum(value * value for value in v))
    return tuple(value / length for value in v) if length > 1e-9 else None


def _rod(start: Point, end: Point, width: float
         ) -> tuple[Point, ...] | None:
    direction = _unit(tuple(b - a for a, b in zip(start, end)))
    if direction is None:
        return None
    right = _unit(_cross(direction, (0.0, 1.0, 0.0)))
    if right is None:
        right = _unit(_cross(direction, (0.0, 0.0, 1.0)))
    assert right is not None
    up = _cross(right, direction)
    half = width / 2.0
    return tuple(tuple(origin[i] + half * (sign_r * right[i]
                                            + sign_u * up[i])
                       for i in range(3))
                 for origin in (start, end)
                 for sign_r, sign_u in ((-1, -1), (1, -1),
                                        (1, 1), (-1, 1)))


_QUADS = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
          (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
_COLORS = {13: "asRedSG", 15: "asBlueSG", 6: "asBlueSG",
           14: "asGreenSG", 17: "asGreen2SG", 22: "asGreen2SG"}


def plan_ik_control_meshes(
    curves: tuple[IKControlCurve, ...], scale: float,
    existing_names: frozenset[str],
) -> tuple[IKControlMeshItem, ...]:
    if not isfinite(scale) or scale <= 0.0:
        raise ValueError("IK Control Mesh 比例必须为正数")
    width = scale / 20.0
    used = set(existing_names)
    plan = []
    for source in curves:
        if (not source.control or not source.curve or not source.global_control
                or len(source.points) < 2 or any(
                    len(point) != 3 or not all(isfinite(v) for v in point)
                    for point in source.points)):
            raise ValueError("IK Control Mesh 曲线数据无效")
        vertices: list[Point] = []
        faces: list[tuple[int, int, int, int]] = []
        pairs = list(zip(source.points, source.points[1:]))
        if source.closed:
            pairs.append((source.points[-1], source.points[0]))
        for start, end in pairs:
            rod = _rod(start, end, width)
            if rod is None:
                continue
            offset = len(vertices)
            vertices.extend(rod)
            faces.extend(tuple(offset + index for index in quad)
                         for quad in _QUADS)
        if not faces:
            continue
        leaf = source.control.rsplit("|", 1)[-1]
        for index in range(99):
            name = leaf + "MeshCtrl" + (str(index) if index else "")
            if name not in used and name + "CurveMPD" not in used \
                    and name + "MeshMPD" not in used:
                used.add(name)
                if source.visibility_source:
                    used.update((name + "CurveMPD", name + "MeshMPD"))
                plan.append(IKControlMeshItem(
                    source.control, source.curve, source.global_control,
                    name, tuple(vertices), tuple(faces),
                    _COLORS.get(source.override_color),
                    source.visibility_source))
                break
        else:
            raise ValueError("IK Control Mesh 名称序号已用完：" + leaf)
    return tuple(plan)
