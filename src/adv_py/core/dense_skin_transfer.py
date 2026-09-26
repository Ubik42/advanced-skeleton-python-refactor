"""Exact dense Skin weights for same-topology influence migration."""
from __future__ import annotations

from array import array
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class DenseSkinWeights:
    skin_name: str
    vertex_count: int
    influence_names: tuple[str, ...]
    values: bytes


def validate_dense_skin(data: DenseSkinWeights) -> None:
    if (not data.skin_name or data.vertex_count < 1
            or not data.influence_names
            or len(data.influence_names) != len(set(data.influence_names))
            or any(not name for name in data.influence_names)):
        raise ValueError("Skin 权重来源或维度无效")
    width = len(data.influence_names)
    if len(data.values) != data.vertex_count * width * 8:
        raise ValueError("Skin 权重字节数与矩阵维度不符")
    values = memoryview(data.values).cast("d")
    for vertex in range(data.vertex_count):
        row = values[vertex * width:(vertex + 1) * width]
        if (any(not isfinite(value) or value < -1e-6 or value > 1.0 + 1e-6
                for value in row) or abs(sum(row) - 1.0) > 1e-6):
            raise ValueError("Skin 顶点权重不是有效归一化分布："
                             f"{vertex} sum={sum(row)} min={min(row)} max={max(row)}")


def reorder_dense_skin(data: DenseSkinWeights, target_skin: str,
                       target_names: tuple[str, ...]) -> DenseSkinWeights:
    validate_dense_skin(data)
    if (not target_skin or len(target_names) != len(data.influence_names)
            or set(target_names) != set(data.influence_names)):
        raise ValueError("目标 Skin 影响关节集合与来源不一致")
    source_index = {name: index for index, name in enumerate(data.influence_names)}
    order = tuple(source_index[name] for name in target_names)
    width = len(order)
    source = memoryview(data.values).cast("d")
    values = array("d", (source[vertex * width + index]
                         for vertex in range(data.vertex_count)
                         for index in order))
    return DenseSkinWeights(target_skin, data.vertex_count,
                            target_names, values.tobytes())
