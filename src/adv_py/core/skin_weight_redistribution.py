"""Explicit one-to-many influence migration for changed joint topology."""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
from math import fsum, isfinite

from .skin_weight_io import (SkinWeightDocument, skin_weight_document_from_state,
                             skin_weight_document_to_json)
from .skin_weights import (SkinInfluenceWeight, SkinVertexWeights,
                           SkinWeightInputState, SkinWeightValidationError)


@dataclass(frozen=True, slots=True)
class SkinWeightRedistributionTarget:
    path: str
    fraction: float


@dataclass(frozen=True, slots=True)
class SkinWeightInfluenceRedistribution:
    source_path: str
    targets: tuple[SkinWeightRedistributionTarget, ...]


@dataclass(frozen=True, slots=True)
class SkinWeightRedistribution:
    target_skin_name: str
    target_mesh_path: str
    target_influence_paths: tuple[str, ...]
    influences: tuple[SkinWeightInfluenceRedistribution, ...]


def redistribute_skin_weight_document(document: SkinWeightDocument,
                                      mapping: SkinWeightRedistribution
                                      ) -> SkinWeightDocument:
    """Preserve each vertex's total weight while explicitly splitting influences."""
    skin_weight_document_to_json(document)
    if not isinstance(mapping, SkinWeightRedistribution):
        raise SkinWeightValidationError("脊柱影响迁移需要明确的重分配文档")
    if (not isinstance(mapping.target_skin_name, str)
            or not mapping.target_skin_name.strip()
            or "|" in mapping.target_skin_name):
        raise SkinWeightValidationError("重分配目标 skinCluster 短名无效")
    if not isinstance(mapping.target_mesh_path, str) or not mapping.target_mesh_path.strip():
        raise SkinWeightValidationError("重分配目标网格路径无效")
    targets = mapping.target_influence_paths
    if (not isinstance(targets, tuple) or not targets
            or any(not isinstance(path, str) or not path.strip() for path in targets)
            or len(set(targets)) != len(targets)):
        raise SkinWeightValidationError("重分配目标影响关节集合无效或重复")
    if not isinstance(mapping.influences, tuple):
        raise SkinWeightValidationError("重分配源影响关节列表无效")
    if any(not isinstance(row, SkinWeightInfluenceRedistribution)
           or not isinstance(row.source_path, str) or not row.source_path.strip()
           for row in mapping.influences):
        raise SkinWeightValidationError("重分配源影响关节路径无效")
    source_paths = tuple(row.source_path for row in mapping.influences)
    if (set(source_paths) != set(document.influence_paths)
            or len(source_paths) != len(document.influence_paths)):
        raise SkinWeightValidationError("重分配必须完整且仅覆盖源影响关节集合")
    target_set = set(targets)
    by_source = {}
    for row in mapping.influences:
        if (not isinstance(row.targets, tuple) or not row.targets
                or any(not isinstance(target, SkinWeightRedistributionTarget)
                       for target in row.targets)):
            raise SkinWeightValidationError("每个源影响关节须至少对应一个目标")
        paths = tuple(target.path for target in row.targets)
        fractions = tuple(target.fraction for target in row.targets)
        if (len(set(paths)) != len(paths)
                or any(path not in target_set for path in paths)
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not isfinite(value) or not 0 < value <= 1 for value in fractions)
                or abs(fsum(fractions) - 1.) > 1e-8):
            raise SkinWeightValidationError("重分配目标须唯一、存在且比例和为 1")
        by_source[row.source_path] = row.targets
    vertices = []
    greatest_count = 0
    for vertex in document.vertices:
        values = {}
        for entry in vertex.weights:
            for target in by_source[entry.influence_path]:
                values.setdefault(target.path, []).append(entry.weight * target.fraction)
        weights = tuple(SkinInfluenceWeight(path, fsum(values[path]))
                        for path in targets if path in values and fsum(values[path]) > 0)
        if abs(fsum(entry.weight for entry in weights) - 1.) > 1e-6:
            raise SkinWeightValidationError("重分配后的顶点权重总量发生变化")
        greatest_count = max(greatest_count, len(weights))
        vertices.append(SkinVertexWeights(vertex.vertex_index, weights))
    state = SkinWeightInputState(mapping.target_skin_name.strip(),
        mapping.target_mesh_path.strip(), document.vertex_count, targets, (),
        max(document.maximum_influences, greatest_count),
        document.maintain_maximum_influences, tuple(vertices))
    return skin_weight_document_from_state(state)


def linear_spine_weight_redistribution(source_chain: tuple[str, ...],
        target_chain: tuple[str, ...], *, target_skin_name: str,
        target_mesh_path: str, other_influences: tuple[tuple[str, str], ...] = (),
        source_positions: tuple[float, ...] | None = None,
        target_positions: tuple[float, ...] | None = None,
        ) -> SkinWeightRedistribution:
    """Map root-to-chest influence positions onto an explicit new chain."""
    if (not isinstance(source_chain, tuple) or not isinstance(target_chain, tuple)
            or not 2 <= len(source_chain) <= 64 or not 2 <= len(target_chain) <= 64
            or len(set(source_chain)) != len(source_chain)
            or len(set(target_chain)) != len(target_chain)
            or any(not isinstance(path, str) or not path.strip()
                   for path in (*source_chain, *target_chain))):
        raise SkinWeightValidationError("脊柱源链与目标链须有 2–64 个唯一关节")
    def positions(values, count):
        if values is None:
            return tuple(index/(count-1) for index in range(count))
        if (not isinstance(values, tuple) or len(values)!=count
                or any(isinstance(value,bool) or not isinstance(value,(int,float))
                       or not isfinite(value) for value in values)
                or values[0]!=0 or values[-1]!=1
                or any(left>=right for left,right in zip(values,values[1:]))):
            raise SkinWeightValidationError("脊柱位置须从 0 到 1 严格递增且与关节数一致")
        return values
    sources=positions(source_positions,len(source_chain))
    targets=positions(target_positions,len(target_chain))
    rows = []
    for index, source in enumerate(source_chain):
        position=sources[index]
        left=min(bisect_right(targets,position)-1,len(targets)-1)
        fraction=(0. if left==len(targets)-1 else
                  (position-targets[left])/(targets[left+1]-targets[left]))
        if fraction>1.-1e-12:
            left+=1
            fraction=0.
        destinations = ((SkinWeightRedistributionTarget(target_chain[left], 1.),)
            if fraction < 1e-12 else (
                SkinWeightRedistributionTarget(target_chain[left], 1. - fraction),
                SkinWeightRedistributionTarget(target_chain[left + 1], fraction)))
        rows.append(SkinWeightInfluenceRedistribution(source, destinations))
    if (not isinstance(other_influences,tuple)
            or any(not isinstance(pair,tuple) or len(pair)!=2
                   or any(not isinstance(path,str) or not path.strip() for path in pair)
                   for pair in other_influences)):
        raise SkinWeightValidationError("其他影响关节须明确一一对应")
    for source, target in other_influences:
        rows.append(SkinWeightInfluenceRedistribution(source,
            (SkinWeightRedistributionTarget(target, 1.),)))
    targets = (*target_chain, *(target for _, target in other_influences))
    if (len(set(row.source_path for row in rows)) != len(rows)
            or len(set(targets)) != len(targets)):
        raise SkinWeightValidationError("脊柱迁移的源或目标影响关节重复")
    return SkinWeightRedistribution(target_skin_name, target_mesh_path,
                                    targets, tuple(rows))
