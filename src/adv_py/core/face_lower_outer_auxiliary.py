"""Plan the 6.925 simpler-eyelid lower Outer auxiliary influence."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping


Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class FaceLowerOuterAuxiliaryInput:
    side: str
    simpler_eyelid: bool
    lower_outer_curve_spans: int
    lower_outer_curve_points: tuple[Vector3, ...]
    vertex_positions: Mapping[int, Vector3]
    adjacency: Mapping[int, frozenset[int]]
    eye_lid_area_vertices: frozenset[int]


@dataclass(frozen=True, slots=True)
class FaceLowerOuterAuxiliaryPlan:
    side: str
    control_name: str
    joint_name: str
    world_position: Vector3
    seed_vertex: int
    smooth_vertices: tuple[int, ...]
    grow_rows: int
    smooth_iterations: int
    seed_weight: float


def plan_face_lower_outer_auxiliary(
    source: FaceLowerOuterAuxiliaryInput,
    *, grow_rows: int = 2, smooth_iterations: int = 5,
    seed_weight: float = .5,
) -> FaceLowerOuterAuxiliaryPlan | None:
    """Select the exterior cheek region around the lower Outer curve.

    In the EYES_ONLY branch of the original MEL, the outer selection grows
    two edge rows before the lower-Outer auxiliary is created. The host
    performs skinCluster smoothWeights on these selected vertices; this
    plan contains no Maya commands or inferred weight values.
    """
    if source.side not in ("R", "L") or type(source.simpler_eyelid) is not bool:
        raise ValueError("眼下外围辅助关节需要明确左右侧与简化眼睑模式")
    if not source.simpler_eyelid:
        return None
    if (type(grow_rows) is not int or grow_rows < 1
            or type(smooth_iterations) is not int
            or smooth_iterations < 1
            or not isfinite(seed_weight)
            or not 0 < seed_weight <= 1):
        raise ValueError("眼下外围扩圈、平滑或种子权重无效")
    points = source.lower_outer_curve_points
    positions = source.vertex_positions
    known_vertices = set(positions)
    midpoint_index = ((source.lower_outer_curve_spans + 1) // 2
                      if type(source.lower_outer_curve_spans) is int else -1)
    if (len(points) < 3
            or type(source.lower_outer_curve_spans) is not int
            or source.lower_outer_curve_spans < 1
            or midpoint_index < 0
            or midpoint_index >= len(points) or not positions
            or any(len(point) != 3 or not all(isfinite(v) for v in point)
                   for point in points)
            or any(type(index) is not int or index < 0
                   or len(position) != 3
                   or not all(isfinite(v) for v in position)
                   for index, position in positions.items())
            or not source.eye_lid_area_vertices <= known_vertices):
        raise ValueError("眼下外围曲线或网格位置无效")
    if (set(source.adjacency) != known_vertices
            or any(not neighbors <= known_vertices
                   for neighbors in source.adjacency.values())):
        raise ValueError("眼下外围网格邻接关系不完整")
    midpoint = points[midpoint_index]
    seed = min(positions, key=lambda index: (
        sum((a - b) ** 2 for a, b in zip(positions[index], midpoint)),
        index))
    selected = {seed}
    for _ in range(grow_rows):
        selected.update(neighbor for index in tuple(selected)
                        for neighbor in source.adjacency[index])
    selected.difference_update(source.eye_lid_area_vertices)
    return FaceLowerOuterAuxiliaryPlan(
        source.side, "lowerLidOuter_" + source.side,
        "lowerLidOuterJoint_" + source.side,
        midpoint, seed, tuple(sorted(selected)),
        grow_rows, smooth_iterations, float(seed_weight))
