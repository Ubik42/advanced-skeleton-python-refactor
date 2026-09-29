"""Plan the original Fit / Create Non-Symmetry Joints toggle."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .fit_hierarchy import (
    FitHierarchyPolicy, FitHierarchySnapshot, audit_fit_hierarchy,
)


@dataclass(frozen=True, slots=True)
class FitNonSymmetryPlan:
    remove_existing: bool
    branch_roots: tuple[str, ...]
    generated_joints: tuple[str, ...]
    center_tolerance: float


def plan_fit_non_symmetry(
    hierarchy: FitHierarchySnapshot, *,
    scale: float,
) -> FitNonSymmetryPlan:
    """Find each side branch whose parent is centered, as MEL does."""
    if (isinstance(scale, bool) or not isinstance(scale, (int, float))
            or not isfinite(scale) or scale <= 0):
        raise ValueError("非对称 Fit 比例无效")
    tolerance = 0.01 * max(float(scale), 0.01)
    generated = tuple(joint.path for joint in hierarchy.joints
                      if joint.short_name.endswith("_NonSymmetry"))
    if generated:
        return FitNonSymmetryPlan(True, (), generated, tolerance)
    issues = audit_fit_hierarchy(hierarchy, FitHierarchyPolicy(
        center_tolerance=tolerance))
    if issues:
        raise ValueError("非对称 Fit 层级无效：" +
                         "；".join(issue.message for issue in issues))
    nodes = {joint.path: joint for joint in hierarchy.joints}
    branches = []
    for joint in hierarchy.joints:
        parent = nodes.get(joint.dag_parent)
        if parent is None:
            continue
        if (abs(joint.world_position[0]) > tolerance
                and abs(parent.world_position[0]) <= tolerance):
            branches.append(joint.path)
    return FitNonSymmetryPlan(False, tuple(branches), (), tolerance)
