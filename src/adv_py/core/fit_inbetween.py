"""Plan the temporary Fit joints used by AdvancedSkeleton Inbetween."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence

from .body_skeleton import FitDeformProfile
from .fit_hierarchy import FitHierarchyNode, FitHierarchySnapshot
from .fit_metadata import FitJointMetadata


class FitInbetweenValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FitInbetweenGuide:
    start_joint: str
    end_joint: str
    index: int
    count: int
    name: str
    parent_name: str
    world_position: tuple[float, float, float]
    deform_profile: FitDeformProfile
    rotation_order: int


@dataclass(frozen=True, slots=True)
class FitInbetweenReparent:
    child_name: str
    parent_guide_name: str


@dataclass(frozen=True, slots=True)
class FitInbetweenPlan:
    guides: tuple[FitInbetweenGuide, ...]
    reparents: tuple[FitInbetweenReparent, ...]


@dataclass(frozen=True, slots=True)
class FitInbetweenGuideState:
    name: str
    parent_name: str
    world_position: tuple[float, float, float]
    deform_profile: FitDeformProfile
    rotation_order: int


def audit_fit_inbetween(
    plan: FitInbetweenPlan,
    states: tuple[FitInbetweenGuideState, ...],
    *,
    tolerance: float = 1e-4,
) -> tuple[str, ...]:
    expected = {guide.name: guide for guide in plan.guides}
    actual = {state.name: state for state in states}
    issues = []
    if len(actual) != len(states) or set(actual) != set(expected):
        issues.append("Inbetween 临时导向关节集合不一致")
    for name, guide in expected.items():
        state = actual.get(name)
        if state is None:
            continue
        if (state.parent_name != guide.parent_name
                or state.deform_profile != guide.deform_profile
                or state.rotation_order != guide.rotation_order
                or any(abs(a - b) > tolerance for a, b in zip(
                    state.world_position, guide.world_position))):
            issues.append("Inbetween 临时导向关节数据不一致：" + name)
    return tuple(issues)


def plan_fit_inbetween(
    hierarchy: FitHierarchySnapshot,
    metadata: tuple[FitJointMetadata, ...],
    profiles: Mapping[str, FitDeformProfile],
    rotation_orders: Mapping[str, int],
    *,
    center_tolerance: float = 0.01,
) -> FitInbetweenPlan:
    """Expand each `inbetweenJoints` value before Body analyzes Fit.

    The host creates these as temporary Fit joints, reparents the original
    downstream joint, and removes the guides after Body construction. This
    plan describes the source hierarchy before either mutation.
    """
    nodes = {node.path: node for node in hierarchy.joints}
    source = {item.joint: item for item in metadata}
    if (len(nodes) != len(hierarchy.joints)
            or len(source) != len(metadata)
            or set(nodes) != set(source)
            or set(nodes) != set(profiles)
            or set(nodes) != set(rotation_orders)):
        raise FitInbetweenValidationError(
            "Inbetween 需要完整且唯一的 Fit 来源数据")
    if not isfinite(center_tolerance) or center_tolerance < 0:
        raise FitInbetweenValidationError(
            "Inbetween 中心容差必须是非负有限数值")
    children: dict[str, list[FitHierarchyNode]] = {}
    names = {node.short_name for node in hierarchy.joints}
    if len(names) != len(hierarchy.joints):
        raise FitInbetweenValidationError("Fit 关节短名必须唯一")
    for node in hierarchy.joints:
        children.setdefault(node.dag_parent or "", []).append(node)
    guides: list[FitInbetweenGuide] = []
    reparents: list[FitInbetweenReparent] = []
    for start in hierarchy.joints:
        count = source[start.path].inbetween_joints or 0
        if count < 0 or count > 10:
            raise FitInbetweenValidationError(
                "Fit inbetweenJoints 必须在 0 到 10 之间：" + start.path)
        if count == 0:
            continue
        end = _rla_child(start, children.get(start.path, ()),
                         center_tolerance)
        if end is None:
            continue
        parent_name = start.short_name
        for index in range(1, count + 1):
            name = start.short_name + "Part" + str(index)
            if name in names:
                raise FitInbetweenValidationError(
                    "Inbetween 临时关节名称冲突：" + name)
            names.add(name)
            fraction = index / (count + 1)
            position = tuple(a + (b - a) * fraction
                             for a, b in zip(start.world_position,
                                             end.world_position))
            guides.append(FitInbetweenGuide(
                start.path, end.path, index, count, name, parent_name,
                position, profiles[start.path].interpolate(
                    profiles[end.path], fraction),
                rotation_orders[start.path],
            ))
            parent_name = name
        reparents.append(FitInbetweenReparent(
            end.short_name, parent_name))
    return FitInbetweenPlan(tuple(guides), tuple(reparents))


def _rla_child(start: FitHierarchyNode,
               candidates: Sequence[FitHierarchyNode],
               tolerance: float) -> FitHierarchyNode | None:
    center = abs(start.world_position[0]) < tolerance
    selected = next((child for child in candidates
                     if (abs(child.world_position[0]) < tolerance)
                     == center), None)
    preference = next((target for key, target in (
        ("Head", "Head"), ("Ankle", "Toes"),
        ("Toes", "Toes"), ("Root", "Spine"))
        if key in start.short_name), None)
    if preference is not None:
        selected = next((child for child in candidates
                         if preference in child.short_name), selected)
    return selected
