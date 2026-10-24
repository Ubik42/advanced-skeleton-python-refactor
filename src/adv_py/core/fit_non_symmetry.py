"""Plan the original Fit / Create Non-Symmetry Joints toggle."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .fit_hierarchy import FitHierarchySnapshot


@dataclass(frozen=True, slots=True)
class FitNonSymmetryPlan:
    remove_existing: bool
    branch_roots: tuple[str, ...]
    generated_joints: tuple[str, ...]
    center_tolerance: float


def plan_fit_non_symmetry(
    hierarchy: FitHierarchySnapshot, *,
    scale: float,
    ordered_paths: tuple[str, ...] | None = None,
) -> FitNonSymmetryPlan:
    """Find each side branch whose parent is centered, as MEL does."""
    if (isinstance(scale, bool) or not isinstance(scale, (int, float))
            or not isfinite(scale) or scale <= 0):
        raise ValueError("非对称 Fit 比例无效")
    tolerance = 0.01 * float(scale)
    generated = tuple(joint.path for joint in hierarchy.joints
                      if joint.short_name.endswith("_NonSymmetry"))
    if generated:
        return FitNonSymmetryPlan(True, (), generated, tolerance)
    nodes = {joint.path: joint for joint in hierarchy.joints}
    if len(nodes) != len(hierarchy.joints):
        raise ValueError('非对称 Fit 关节身份重复')
    if ordered_paths is None:
        ordered_paths = tuple(nodes)
    elif (len(set(ordered_paths)) != len(ordered_paths)
            or any(path not in nodes for path in ordered_paths)):
        raise ValueError('非对称 Fit 原版遍历顺序包含重复或未知关节')
    branches = []
    for path in ordered_paths:
        joint = nodes[path]
        parent = nodes.get(joint.dag_parent)
        if parent is None:
            continue
        if (abs(joint.world_position[0]) > tolerance
                and abs(parent.world_position[0]) <= tolerance):
            branches.append(joint.path)
    return FitNonSymmetryPlan(False, tuple(branches), (), tolerance)
