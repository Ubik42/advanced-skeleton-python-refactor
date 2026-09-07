from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


class SkinWeightValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SkinInfluenceWeight:
    influence_path: str
    weight: float


@dataclass(frozen=True, slots=True)
class SkinVertexWeights:
    vertex_index: int
    weights: tuple[SkinInfluenceWeight, ...]


@dataclass(frozen=True, slots=True)
class SkinWeightEditRequest:
    skin_name: str
    mesh_path: str
    vertices: tuple[SkinVertexWeights, ...]


@dataclass(frozen=True, slots=True)
class SkinWeightInputState:
    skin_name: str | None
    geometry_path: str | None
    vertex_count: int
    influence_paths: tuple[str, ...]
    locked_influences: tuple[str, ...]
    maximum_influences: int
    maintain_maximum_influences: bool
    vertices: tuple[SkinVertexWeights, ...]


@dataclass(frozen=True, slots=True)
class SkinWeightChange:
    vertex_index: int
    before: tuple[SkinInfluenceWeight, ...]
    after: tuple[SkinInfluenceWeight, ...]


@dataclass(frozen=True, slots=True)
class SkinWeightIssue:
    code: str
    message: str
    subject: str | None = None


def skin_weight_request(
    skin_name: str,
    mesh_path: str,
    vertices: tuple[SkinVertexWeights, ...],
    *,
    tolerance: float = 1e-6,
) -> SkinWeightEditRequest:
    if (
        not isinstance(skin_name, str)
        or not skin_name.strip()
        or "|" in skin_name
    ):
        raise SkinWeightValidationError("权重编辑需要有效的 skinCluster 短名")
    if not isinstance(mesh_path, str) or not mesh_path.strip():
        raise SkinWeightValidationError("权重编辑需要显式 mesh 路径")
    if not vertices:
        raise SkinWeightValidationError("权重编辑至少需要一个顶点")
    if len({vertex.vertex_index for vertex in vertices}) != len(vertices):
        raise SkinWeightValidationError("权重编辑不能重复声明同一顶点")

    canonical = []
    for vertex in vertices:
        if (
            isinstance(vertex.vertex_index, bool)
            or not isinstance(vertex.vertex_index, int)
            or vertex.vertex_index < 0
        ):
            raise SkinWeightValidationError("顶点索引必须是非负整数")
        if not vertex.weights:
            raise SkinWeightValidationError("每个顶点至少需要一个非零 influence")
        raw_paths = [entry.influence_path for entry in vertex.weights]
        if any(
            not isinstance(path, str) or not path.strip()
            for path in raw_paths
        ):
            raise SkinWeightValidationError("Influence 路径不能为空")
        paths = [path.strip() for path in raw_paths]
        if len(set(paths)) != len(paths):
            raise SkinWeightValidationError("同一顶点不能重复声明 influence")
        values = [entry.weight for entry in vertex.weights]
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value <= 0.0
            or value > 1.0
            for value in values
        ):
            raise SkinWeightValidationError("Influence 权重必须是大于 0 且不超过 1 的有限数")
        if abs(sum(values) - 1.0) > tolerance:
            raise SkinWeightValidationError("每个顶点的 influence 权重和必须为 1")
        weights = tuple(
            sorted(
                (
                    SkinInfluenceWeight(path, float(entry.weight))
                    for path, entry in zip(paths, vertex.weights)
                ),
                key=lambda entry: entry.influence_path,
            )
        )
        canonical.append(SkinVertexWeights(vertex.vertex_index, weights))
    return SkinWeightEditRequest(
        skin_name.strip(),
        mesh_path.strip(),
        tuple(sorted(canonical, key=lambda vertex: vertex.vertex_index)),
    )


def audit_skin_weight_input(
    request: SkinWeightEditRequest,
    state: SkinWeightInputState,
) -> tuple[SkinWeightIssue, ...]:
    issues = []
    if state.skin_name != request.skin_name:
        issues.append(
            SkinWeightIssue(
                "skin_missing",
                "skinCluster 不存在、名称不唯一或类型错误",
                request.skin_name,
            )
        )
    if state.geometry_path != request.mesh_path:
        issues.append(
            SkinWeightIssue(
                "geometry_mismatch",
                "skinCluster 没有唯一绑定到目标 mesh",
                request.mesh_path,
            )
        )
    if state.vertex_count <= 0:
        issues.append(SkinWeightIssue("mesh_empty", "目标 mesh 没有可编辑顶点", request.mesh_path))
    available = set(state.influence_paths)
    locked = set(state.locked_influences)
    for vertex in request.vertices:
        if vertex.vertex_index >= state.vertex_count:
            issues.append(
                SkinWeightIssue(
                    "vertex_out_of_range",
                    "顶点索引超出 mesh 范围",
                    str(vertex.vertex_index),
                )
            )
        for entry in vertex.weights:
            if entry.influence_path not in available:
                issues.append(
                    SkinWeightIssue(
                        "influence_missing",
                        "目标 influence 不属于该 skinCluster",
                        entry.influence_path,
                    )
                )
            elif entry.influence_path in locked:
                issues.append(
                    SkinWeightIssue(
                        "influence_locked",
                        "目标 influence 已锁定权重",
                        entry.influence_path,
                    )
                )
        if state.maintain_maximum_influences and len(vertex.weights) > state.maximum_influences:
            issues.append(
                SkinWeightIssue(
                    "too_many_influences",
                    "顶点权重超过 skinCluster 最大影响数",
                    str(vertex.vertex_index),
                )
            )
    wanted_indices = {
        vertex.vertex_index
        for vertex in request.vertices
        if vertex.vertex_index < state.vertex_count
    }
    captured_indices = {vertex.vertex_index for vertex in state.vertices}
    if wanted_indices != captured_indices:
        issues.append(
            SkinWeightIssue(
                "weight_snapshot_incomplete",
                "未能完整读取目标顶点权重",
            )
        )
    return tuple(issues)


def plan_skin_weight_changes(
    request: SkinWeightEditRequest,
    state: SkinWeightInputState,
    *,
    tolerance: float = 1e-6,
) -> tuple[SkinWeightChange, ...]:
    if audit_skin_weight_input(request, state):
        return ()
    current = {vertex.vertex_index: vertex.weights for vertex in state.vertices}
    changes = []
    for vertex in request.vertices:
        before = _canonical_weights(current[vertex.vertex_index], tolerance)
        after = _canonical_weights(vertex.weights, tolerance)
        if not _weights_close(before, after, tolerance):
            changes.append(SkinWeightChange(vertex.vertex_index, before, after))
    return tuple(changes)


def audit_skin_weight_result(
    request: SkinWeightEditRequest,
    state: SkinWeightInputState,
    *,
    tolerance: float = 1e-5,
) -> tuple[SkinWeightIssue, ...]:
    issues = list(audit_skin_weight_input(request, state))
    actual = {vertex.vertex_index: vertex.weights for vertex in state.vertices}
    for vertex in request.vertices:
        weights = actual.get(vertex.vertex_index)
        if weights is not None and not _weights_close(
            _canonical_weights(vertex.weights, tolerance),
            _canonical_weights(weights, tolerance),
            tolerance,
        ):
            issues.append(
                SkinWeightIssue(
                    "weight_mismatch",
                    "顶点权重与计划结果不一致",
                    str(vertex.vertex_index),
                )
            )
    return tuple(issues)


def _canonical_weights(
    weights: tuple[SkinInfluenceWeight, ...],
    tolerance: float,
) -> tuple[SkinInfluenceWeight, ...]:
    return tuple(
        sorted(
            (entry for entry in weights if abs(entry.weight) > tolerance),
            key=lambda entry: entry.influence_path,
        )
    )


def _weights_close(left, right, tolerance):
    return (
        len(left) == len(right)
        and all(
            a.influence_path == b.influence_path
            and abs(a.weight - b.weight) <= tolerance
            for a, b in zip(left, right)
        )
    )
