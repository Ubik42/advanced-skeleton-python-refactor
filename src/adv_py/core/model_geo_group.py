"""Plan the Model Cleaner 'Create geo' preparation step."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelAssembly:
    path: str
    node_type: str
    shape_types: tuple[str, ...]
    locked: bool


@dataclass(frozen=True, slots=True)
class ModelGeoGroupPlan:
    create_geo: bool
    move_paths: tuple[str, ...]


def plan_model_geo_group(
    assemblies: tuple[ModelAssembly, ...],
) -> ModelGeoGroupPlan:
    if len({node.path for node in assemblies}) != len(assemblies):
        raise ValueError("模型场景有重复的顶层对象")
    if any(not node.path.startswith("|") or node.path.count("|") != 1
           for node in assemblies):
        raise ValueError("Model Clean Create geo 需要顶层 DAG 对象")
    geo = next((node for node in assemblies if node.path == "|geo"), None)
    if geo is not None and (geo.node_type != "transform"
                            or geo.shape_types or geo.locked):
        raise ValueError("已有 |geo 不是可编辑的空 Transform 组")
    moves = tuple(node.path for node in assemblies
                  if node.path != "|geo" and node.node_type == "transform"
                  and (not node.shape_types
                       or node.shape_types[0] == "mesh"))
    if any(node.locked for node in assemblies
           if node.path in moves):
        raise ValueError("待归入 geo 的模型对象已锁定")
    return ModelGeoGroupPlan(geo is None, moves)
