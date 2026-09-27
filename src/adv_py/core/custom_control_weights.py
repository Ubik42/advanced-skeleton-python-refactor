"""Scene-independent conversion of measured SoftMod motion to Cluster weights."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re

from .custom_controller import WeightedVertex


@dataclass(frozen=True, slots=True)
class SoftModProbe:
    """World-space mesh points before and after a one-unit Y handle move."""

    rest: tuple[tuple[float, float, float], ...]
    moved: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True, slots=True)
class ClusterWeightTransfer:
    weights: tuple[WeightedVertex, ...]
    attachment_vertex: int


def cluster_weights_from_probe(probe: SoftModProbe) -> ClusterWeightTransfer:
    """Match ADV's Y-displacement probe, retaining the strongest vertex."""
    if not probe.rest or len(probe.rest) != len(probe.moved):
        raise ValueError("SoftMod 位移采样的顶点数量不一致")
    weights = []
    for index, (rest, moved) in enumerate(zip(probe.rest, probe.moved)):
        if (len(rest) != 3 or len(moved) != 3
                or any(not isfinite(value) for value in (*rest, *moved))):
            raise ValueError("SoftMod 位移采样含无效坐标")
        weight = moved[1] - rest[1]
        if not -1e-5 <= weight <= 1.00001:
            raise ValueError("SoftMod 位移不符合单位 Y 探测范围")
        weights.append(WeightedVertex(index, max(0.0, min(1.0, weight))))
    strongest = max(weights, key=lambda item: (item.weight, -item.index))
    if strongest.weight <= 0:
        raise ValueError("SoftMod 位移探测未产生 Cluster 权重")
    return ClusterWeightTransfer(tuple(weights), strongest.index)


def paired_cluster_control_name(control_name: str) -> tuple[str, str]:
    """Return the opposite control name and source side for an L/R control."""
    match = re.fullmatch(r"(.+)_([LR])Control", control_name)
    if not match:
        raise ValueError("Cluster 镜像要求控制器名称以 _LControl 或 _RControl 结尾")
    stem, side = match.groups()
    opposite = "L" if side == "R" else "R"
    return stem + "_" + opposite + "Control", side
