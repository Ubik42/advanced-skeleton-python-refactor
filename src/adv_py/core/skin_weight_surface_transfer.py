"""Interpolate complete skin weights across explicitly captured mesh surfaces."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .face_shapes import FaceMeshSnapshot
from .face_surface_transfer import FaceSurfaceAlignment, Triangle, project_mesh_surface
from .skin_weight_io import (SkinWeightDocument, skin_weight_document_from_state,
                             skin_weight_document_to_json)
from .skin_weights import (SkinInfluenceWeight, SkinVertexWeights,
                           SkinWeightInputState, SkinWeightValidationError)


@dataclass(frozen=True, slots=True)
class SkinWeightSurfaceTransferResult:
    document: SkinWeightDocument
    source_triangle_count: int
    max_surface_distance: float
    max_discarded_weight: float
    blend_weights: tuple[float, ...] | None = None
    member_vertices: tuple[int, ...] | None = None


def transfer_skin_weights_by_surface(
    source: SkinWeightDocument,
    source_mesh: FaceMeshSnapshot,
    target_mesh: FaceMeshSnapshot,
    source_triangles: tuple[Triangle, ...],
    target_state: SkinWeightInputState,
    *,
    max_distance: float,
    max_discarded_weight: float = 0.0,
    alignment: FaceSurfaceAlignment | None = None,
    allow_target_extra_influences: bool = False,
    source_blend_weights: tuple[float, ...] | None = None,
    source_member_vertices: tuple[int, ...] | None = None,
) -> SkinWeightSurfaceTransferResult:
    """Build a complete target document without modifying either mesh."""
    skin_weight_document_to_json(source)
    if (source.mesh_path not in (source_mesh.path, target_mesh.path)
            or source.vertex_count != source_mesh.vertex_count):
        raise SkinWeightValidationError("源权重文档与源网格快照不匹配")
    if target_state.geometry_path != target_mesh.path or target_state.vertex_count != target_mesh.vertex_count:
        raise SkinWeightValidationError("目标 skinCluster 与目标网格快照不匹配")
    if not target_state.skin_name or not target_state.influence_paths:
        raise SkinWeightValidationError("目标 skinCluster 或 influence 集合无效")
    if not isinstance(allow_target_extra_influences, bool):
        raise SkinWeightValidationError("额外目标关节策略必须是布尔值")
    source_influences = set(source.influence_paths)
    target_influences = set(target_state.influence_paths)
    if (not source_influences.issubset(target_influences)
            or (not allow_target_extra_influences
                and source_influences != target_influences)):
        raise SkinWeightValidationError("源权重与目标 skinCluster 的 influence 集合不同")
    if target_state.locked_influences:
        raise SkinWeightValidationError("目标 skinCluster 有锁定的 influence")
    if (source_blend_weights is not None
            and (not isinstance(source_blend_weights, tuple)
                 or len(source_blend_weights) != source.vertex_count
                 or any(isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not isfinite(value) or not 0.0 <= value <= 1.0
                        for value in source_blend_weights))):
        raise SkinWeightValidationError("来源逐顶点混合权重无效")
    if (source_member_vertices is not None
            and (not isinstance(source_member_vertices, tuple)
                 or not source_member_vertices
                 or any(type(index) is not int or index < 0
                        or index >= source.vertex_count
                        for index in source_member_vertices)
                 or tuple(sorted(set(source_member_vertices)))
                 != source_member_vertices)):
        raise SkinWeightValidationError("来源 Skin 变形集顶点成员无效")
    if (isinstance(max_discarded_weight, bool)
            or not isinstance(max_discarded_weight, (int, float))
            or not isfinite(max_discarded_weight)
            or not 0.0 <= max_discarded_weight < 1.0):
        raise SkinWeightValidationError("允许裁剪的最大权重损失须在 [0, 1) 内")
    if (isinstance(target_state.maximum_influences, bool)
            or not isinstance(target_state.maximum_influences, int)
            or target_state.maximum_influences < 1):
        raise SkinWeightValidationError("目标最大影响数无效")
    projection = project_mesh_surface(source_mesh, target_mesh, source_triangles,
                                      max_distance=max_distance, alignment=alignment)
    source_rows = {row.vertex_index: row.weights for row in source.vertices}
    vertices = []
    blend_weights = [] if source_blend_weights is not None else None
    source_members = (set(source_member_vertices)
                      if source_member_vertices is not None else None)
    target_members = [] if source_members is not None else None
    greatest_discard = 0.0
    for target_index, projected in enumerate(projection.rows):
        triangle = source_triangles[projected.triangle_index]
        if target_members is not None:
            coverage = sum(coefficient for source_index, coefficient
                in zip(triangle, projected.barycentric)
                if source_index in source_members)
            if coverage >= 0.5:
                target_members.append(target_index)
        if blend_weights is not None:
            value = sum(source_blend_weights[source_index]
                * coefficient for source_index, coefficient in zip(
                    triangle, projected.barycentric))
            if not -1e-8 <= value <= 1.0 + 1e-8:
                raise SkinWeightValidationError(
                    f"目标顶点 {target_index} 的混合权重投射超出范围")
            blend_weights.append(min(1.0, max(0.0, value)))
        values: dict[str, float] = {}
        for source_index, coefficient in zip(triangle,
                                             projected.barycentric):
            for entry in source_rows[source_index]:
                values[entry.influence_path] = values.get(entry.influence_path, 0.0) + coefficient * entry.weight
        threshold = 1e-12 if source.normalized else 0.0
        ranked = sorted(((path, weight) for path, weight in values.items()
                         if weight > threshold),
                        key=lambda item: (-item[1], item[0]))
        if not ranked and source.normalized:
            raise SkinWeightValidationError(f"目标顶点 {target_index} 没有可转移权重")
        if target_state.maintain_maximum_influences:
            retained = ranked[:target_state.maximum_influences]
            discarded = sum(weight for _, weight in ranked[target_state.maximum_influences:])
        else:
            retained, discarded = ranked, 0.0
        source_total = sum(weight for _, weight in ranked)
        discarded_fraction = (discarded / source_total
                              if source_total > 0.0 else 0.0)
        greatest_discard = max(greatest_discard, discarded_fraction)
        if discarded_fraction > max_discarded_weight + 1e-12:
            raise SkinWeightValidationError(
                f"目标顶点 {target_index} 的影响数裁剪损失 {discarded_fraction:.6g} 超过上限")
        total = sum(weight for _, weight in retained)
        vertices.append(SkinVertexWeights(target_index, tuple(
            SkinInfluenceWeight(path, weight / total *
                (1.0 if source.normalized else source_total))
            for path, weight in retained) if total else ()))
    state = SkinWeightInputState(target_state.skin_name, target_state.geometry_path,
        target_state.vertex_count, target_state.influence_paths, (),
        target_state.maximum_influences, target_state.maintain_maximum_influences,
        tuple(vertices))
    document = skin_weight_document_from_state(state,
        preserve_raw=not source.normalized)
    if target_members is not None and not target_members:
        raise SkinWeightValidationError(
            "表面投射后的 Skin 变形集没有受影响顶点")
    return SkinWeightSurfaceTransferResult(document, len(source_triangles),
                                           projection.max_distance, greatest_discard,
                                           tuple(blend_weights)
                                           if blend_weights is not None else None,
                                           tuple(target_members)
                                           if target_members is not None else None)
