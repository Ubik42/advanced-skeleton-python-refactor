from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import product
from math import floor, isfinite, sqrt

from .skin_weight_io import SkinWeightInfluenceMapping
from .skin_weight_mirror import SkinWeightVertexPair, skin_weight_mirror_request
from .skin_weights import SkinWeightIssue, SkinWeightValidationError


class SkinWeightMirrorDirection(str, Enum):
    NEGATIVE_TO_POSITIVE = "negative_to_positive"
    POSITIVE_TO_NEGATIVE = "positive_to_negative"


@dataclass(frozen=True, slots=True)
class SkinMeshVertexPosition:
    vertex_index: int
    position: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class SkinMeshGeometryState:
    mesh_path: str | None
    vertex_count: int
    vertices: tuple[SkinMeshVertexPosition, ...]


@dataclass(frozen=True, slots=True)
class SkinWeightGeometryMirrorRequest:
    skin_name: str
    mesh_path: str
    direction: SkinWeightMirrorDirection
    plane_origin_x: float
    tolerance: float
    influences: tuple[SkinWeightInfluenceMapping, ...]


def skin_weight_geometry_mirror_request(
    skin_name: str,
    mesh_path: str,
    direction: SkinWeightMirrorDirection,
    influences: tuple[SkinWeightInfluenceMapping, ...],
    *,
    plane_origin_x: float = 0.0,
    tolerance: float = 1e-5,
) -> SkinWeightGeometryMirrorRequest:
    if not isinstance(direction, SkinWeightMirrorDirection):
        raise SkinWeightValidationError("几何权重镜像需要显式方向")
    if (
        not isinstance(plane_origin_x, (int, float))
        or isinstance(plane_origin_x, bool)
        or not isfinite(plane_origin_x)
    ):
        raise SkinWeightValidationError("镜像平面 X 原点必须是有限数")
    if (
        not isinstance(tolerance, (int, float))
        or isinstance(tolerance, bool)
        or not isfinite(tolerance)
        or tolerance <= 0.0
    ):
        raise SkinWeightValidationError("几何配对容差必须是正有限数")

    # Reuse the explicit mirror contract to validate names and influence bijection.
    probe = skin_weight_mirror_request(
        skin_name,
        mesh_path,
        (SkinWeightVertexPair(0, 1),),
        influences,
    )
    return SkinWeightGeometryMirrorRequest(
        probe.skin_name,
        probe.mesh_path,
        direction,
        float(plane_origin_x),
        float(tolerance),
        probe.influences,
    )


def plan_skin_weight_geometry_pairs(
    request: SkinWeightGeometryMirrorRequest,
    state: SkinMeshGeometryState,
) -> tuple[tuple[SkinWeightVertexPair, ...], tuple[SkinWeightIssue, ...]]:
    issues: list[SkinWeightIssue] = []
    if state.mesh_path != request.mesh_path:
        issues.append(
            SkinWeightIssue(
                "geometry_missing",
                "mesh 不存在、名称不唯一或不是单一 polygon transform",
                request.mesh_path,
            )
        )
    if state.vertex_count <= 0:
        issues.append(SkinWeightIssue("mesh_empty", "目标 mesh 没有顶点", request.mesh_path))

    indices = [vertex.vertex_index for vertex in state.vertices]
    expected = set(range(max(0, state.vertex_count)))
    if len(indices) != len(set(indices)) or set(indices) != expected:
        issues.append(
            SkinWeightIssue(
                "geometry_snapshot_incomplete",
                "未能完整且唯一地读取全部顶点位置",
                request.mesh_path,
            )
        )
    invalid_positions = tuple(
        vertex.vertex_index
        for vertex in state.vertices
        if len(vertex.position) != 3
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(value)
            for value in vertex.position
        )
    )
    if invalid_positions:
        issues.append(
            SkinWeightIssue(
                "vertex_position_invalid",
                "顶点世界位置包含无效数值",
                str(invalid_positions[0]),
            )
        )
    if issues:
        return (), tuple(issues)

    negative_to_positive = (
        request.direction is SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE
    )
    source = []
    target = []
    for vertex in state.vertices:
        distance = vertex.position[0] - request.plane_origin_x
        if abs(distance) <= request.tolerance:
            continue
        if (distance < 0.0) is negative_to_positive:
            source.append(vertex)
        else:
            target.append(vertex)

    if not source:
        issues.append(SkinWeightIssue("source_side_empty", "镜像源侧没有离开中心面的顶点"))
    if not target:
        issues.append(SkinWeightIssue("target_side_empty", "镜像目标侧没有离开中心面的顶点"))
    if len(source) != len(target):
        issues.append(
            SkinWeightIssue(
                "side_vertex_count_mismatch",
                "镜像平面两侧的顶点数量不一致",
                f"{len(source)} != {len(target)}",
            )
        )
    if issues:
        return (), tuple(issues)

    target_buckets: dict[
        tuple[int, int, int],
        list[SkinMeshVertexPosition],
    ] = {}
    for target_vertex in target:
        target_buckets.setdefault(
            _position_cell(target_vertex.position, request.tolerance),
            [],
        ).append(target_vertex)

    pairs = []
    used_targets: set[int] = set()
    for source_vertex in sorted(source, key=lambda vertex: vertex.vertex_index):
        x, y, z = source_vertex.position
        reflected = (2.0 * request.plane_origin_x - x, y, z)
        reflected_cell = _position_cell(reflected, request.tolerance)
        candidates = (
            target_vertex
            for offset in product((-1, 0, 1), repeat=3)
            for target_vertex in target_buckets.get(
                tuple(
                    reflected_cell[axis] + offset[axis]
                    for axis in range(3)
                ),
                (),
            )
        )
        matches = sorted(
            (
                target_vertex
                for target_vertex in candidates
                if _distance(target_vertex.position, reflected) <= request.tolerance
            ),
            key=lambda vertex: vertex.vertex_index,
        )
        if not matches:
            issues.append(
                SkinWeightIssue(
                    "mirrored_vertex_missing",
                    "源顶点在目标侧没有容差内的镜像位置",
                    str(source_vertex.vertex_index),
                )
            )
            continue
        if len(matches) > 1:
            issues.append(
                SkinWeightIssue(
                    "mirrored_vertex_ambiguous",
                    "源顶点在目标侧匹配到多个候选",
                    str(source_vertex.vertex_index),
                )
            )
            continue
        target_vertex = matches[0]
        if target_vertex.vertex_index in used_targets:
            issues.append(
                SkinWeightIssue(
                    "mirrored_target_reused",
                    "多个源顶点匹配到同一目标顶点",
                    str(target_vertex.vertex_index),
                )
            )
            continue
        used_targets.add(target_vertex.vertex_index)
        pairs.append(
            SkinWeightVertexPair(
                source_vertex.vertex_index,
                target_vertex.vertex_index,
            )
        )

    unmatched_targets = sorted(
        vertex.vertex_index
        for vertex in target
        if vertex.vertex_index not in used_targets
    )
    if unmatched_targets:
        issues.append(
            SkinWeightIssue(
                "target_vertex_unmatched",
                "目标侧存在没有源顶点对应的位置",
                str(unmatched_targets[0]),
            )
        )
    return (() if issues else tuple(pairs)), tuple(issues)


def _distance(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def _position_cell(
    position: tuple[float, float, float],
    cell_size: float,
) -> tuple[int, int, int]:
    return tuple(floor(value / cell_size) for value in position)  # type: ignore[return-value]
