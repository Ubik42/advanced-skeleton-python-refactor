from __future__ import annotations

from dataclasses import dataclass

from .skin_weight_io import SkinWeightInfluenceMapping
from .skin_weights import (
    SkinInfluenceWeight,
    SkinVertexWeights,
    SkinWeightInputState,
    SkinWeightIssue,
    SkinWeightValidationError,
    skin_weight_request,
)


@dataclass(frozen=True, slots=True)
class SkinWeightVertexPair:
    source_index: int
    target_index: int


@dataclass(frozen=True, slots=True)
class SkinWeightMirrorRequest:
    skin_name: str
    mesh_path: str
    vertex_pairs: tuple[SkinWeightVertexPair, ...]
    influences: tuple[SkinWeightInfluenceMapping, ...]


def skin_weight_mirror_request(
    skin_name: str,
    mesh_path: str,
    vertex_pairs: tuple[SkinWeightVertexPair, ...],
    influences: tuple[SkinWeightInfluenceMapping, ...],
) -> SkinWeightMirrorRequest:
    if (
        not isinstance(skin_name, str)
        or not skin_name.strip()
        or "|" in skin_name
    ):
        raise SkinWeightValidationError("权重镜像需要有效的 skinCluster 短名")
    if not isinstance(mesh_path, str) or not mesh_path.strip():
        raise SkinWeightValidationError("权重镜像需要显式 mesh 路径")
    if not vertex_pairs:
        raise SkinWeightValidationError("权重镜像至少需要一个顶点对")
    canonical_pairs = []
    for pair in vertex_pairs:
        values = (pair.source_index, pair.target_index)
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for value in values
        ):
            raise SkinWeightValidationError("镜像顶点索引必须是非负整数")
        if pair.source_index == pair.target_index:
            raise SkinWeightValidationError("镜像顶点源与目标不能相同")
        canonical_pairs.append(pair)
    sources = [pair.source_index for pair in canonical_pairs]
    targets = [pair.target_index for pair in canonical_pairs]
    if len(set(sources)) != len(sources):
        raise SkinWeightValidationError("镜像顶点源不能重复")
    if len(set(targets)) != len(targets):
        raise SkinWeightValidationError("镜像顶点目标不能重复")
    if set(sources) & set(targets):
        raise SkinWeightValidationError("镜像源与目标顶点集合必须互不重叠")
    if not influences:
        raise SkinWeightValidationError("权重镜像至少需要一条 influence 映射")
    canonical_influences = []
    for entry in influences:
        if (
            not isinstance(entry.source_path, str)
            or not entry.source_path.strip()
            or not isinstance(entry.target_path, str)
            or not entry.target_path.strip()
        ):
            raise SkinWeightValidationError("镜像 influence 路径不能为空")
        canonical_influences.append(
            SkinWeightInfluenceMapping(
                entry.source_path.strip(),
                entry.target_path.strip(),
            )
        )
    influence_sources = [entry.source_path for entry in canonical_influences]
    influence_targets = [entry.target_path for entry in canonical_influences]
    if len(set(influence_sources)) != len(influence_sources):
        raise SkinWeightValidationError("镜像 influence 源不能重复")
    if len(set(influence_targets)) != len(influence_targets):
        raise SkinWeightValidationError("镜像 influence 目标必须一一对应")
    return SkinWeightMirrorRequest(
        skin_name.strip(),
        mesh_path.strip(),
        tuple(sorted(canonical_pairs, key=lambda pair: pair.source_index)),
        tuple(canonical_influences),
    )


def audit_skin_weight_mirror_input(
    request: SkinWeightMirrorRequest,
    source: SkinWeightInputState,
    target: SkinWeightInputState,
) -> tuple[SkinWeightIssue, ...]:
    issues = []
    for label, state in (("源", source), ("目标", target)):
        if state.skin_name != request.skin_name:
            issues.append(
                SkinWeightIssue(
                    "skin_mismatch",
                    f"镜像{label} skinCluster 不一致",
                    request.skin_name,
                )
            )
        if state.geometry_path != request.mesh_path:
            issues.append(
                SkinWeightIssue(
                    "geometry_mismatch",
                    f"镜像{label} mesh 不一致",
                    request.mesh_path,
                )
            )
    if source.vertex_count <= 0 or source.vertex_count != target.vertex_count:
        issues.append(
            SkinWeightIssue(
                "vertex_count_mismatch",
                "镜像源与目标顶点数无效或不一致",
                request.mesh_path,
            )
        )
    source_indices = {pair.source_index for pair in request.vertex_pairs}
    target_indices = {pair.target_index for pair in request.vertex_pairs}
    if any(index >= source.vertex_count for index in source_indices | target_indices):
        issues.append(
            SkinWeightIssue(
                "vertex_out_of_range",
                "镜像顶点索引超出 mesh 范围",
                request.mesh_path,
            )
        )
    if {vertex.vertex_index for vertex in source.vertices} != {
        index for index in source_indices if index < source.vertex_count
    }:
        issues.append(SkinWeightIssue("source_snapshot_incomplete", "镜像源权重快照不完整"))
    if {vertex.vertex_index for vertex in target.vertices} != {
        index for index in target_indices if index < target.vertex_count
    }:
        issues.append(SkinWeightIssue("target_snapshot_incomplete", "镜像目标权重快照不完整"))
    source_available = set(source.influence_paths)
    target_available = set(target.influence_paths)
    target_locked = set(target.locked_influences)
    for entry in request.influences:
        if entry.source_path not in source_available:
            issues.append(SkinWeightIssue("source_influence_missing", "镜像源 influence 不属于 skinCluster", entry.source_path))
        if entry.target_path not in target_available:
            issues.append(SkinWeightIssue("target_influence_missing", "镜像目标 influence 不属于 skinCluster", entry.target_path))
        elif entry.target_path in target_locked:
            issues.append(SkinWeightIssue("target_influence_locked", "镜像目标 influence 已锁定权重", entry.target_path))
    mapped_sources = {entry.source_path for entry in request.influences}
    for vertex in source.vertices:
        for weight in vertex.weights:
            if weight.influence_path not in mapped_sources:
                issues.append(SkinWeightIssue("unmapped_source_influence", "镜像源顶点包含未映射 influence", weight.influence_path))
    return tuple(issues)


def plan_skin_weight_mirror(
    request: SkinWeightMirrorRequest,
    source: SkinWeightInputState,
    target: SkinWeightInputState,
) -> tuple[SkinVertexWeights, ...]:
    if audit_skin_weight_mirror_input(request, source, target):
        return ()
    source_by_index = {
        vertex.vertex_index: vertex
        for vertex in source.vertices
    }
    target_by_source = {
        entry.source_path: entry.target_path
        for entry in request.influences
    }
    vertices = tuple(
        SkinVertexWeights(
            pair.target_index,
            tuple(
                SkinInfluenceWeight(
                    target_by_source[weight.influence_path],
                    weight.weight,
                )
                for weight in source_by_index[pair.source_index].weights
            ),
        )
        for pair in request.vertex_pairs
    )
    return skin_weight_request(
        request.skin_name,
        request.mesh_path,
        vertices,
    ).vertices
