from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .fit_hierarchy import FitHierarchySnapshot, audit_fit_hierarchy
from .fit_metadata import FitJointMetadata, audit_fit_joint


Vector3 = tuple[float, float, float]


class FitSymmetryValidationError(ValueError):
    """Raised when Fit joints cannot be expanded into build-side instances."""


class FitBuildSide(str, Enum):
    MIDDLE = "M"
    RIGHT = "R"
    LEFT = "L"


@dataclass(frozen=True, slots=True)
class FitSymmetryInstance:
    source_joint: str
    output_path: str
    output_name: str
    parent_output_path: str | None
    side: FitBuildSide
    world_position: Vector3
    mirrored: bool


def expand_fit_symmetry(
    hierarchy: FitHierarchySnapshot,
    metadata: tuple[FitJointMetadata, ...],
    *,
    center_tolerance: float = 0.01,
) -> tuple[FitSymmetryInstance, ...]:
    """Expand one center/right Fit source tree into M/R/L build instances."""

    if (
        isinstance(center_tolerance, bool)
        or not isinstance(center_tolerance, (int, float))
        or not isfinite(float(center_tolerance))
        or center_tolerance < 0
    ):
        raise FitSymmetryValidationError("镜像中心容差必须是非负有限数值")
    hierarchy_issues = audit_fit_hierarchy(hierarchy)
    if hierarchy_issues:
        raise FitSymmetryValidationError(
            "FitSkeleton 镜像分析失败："
            + "；".join(issue.message for issue in hierarchy_issues)
        )

    nodes = {node.path: node for node in hierarchy.joints}
    metadata_by_joint = {item.joint: item for item in metadata}
    if len(metadata_by_joint) != len(metadata) or set(metadata_by_joint) != set(nodes):
        raise FitSymmetryValidationError("镜像分析需要每个 Fit joint 的完整元数据")
    metadata_issues = tuple(
        issue for item in metadata for issue in audit_fit_joint(item)
    )
    if metadata_issues:
        raise FitSymmetryValidationError(
            "Fit joint 镜像元数据无效："
            + "；".join(issue.message for issue in metadata_issues)
        )

    source_side: dict[str, FitBuildSide] = {}
    inherited_no_mirror: dict[str, bool] = {}
    inherited_left_only: dict[str, bool] = {}
    output_paths: dict[tuple[str, FitBuildSide], str] = {}
    instances: list[FitSymmetryInstance] = []

    ordered = sorted(hierarchy.joints, key=lambda node: (node.path.count("|"), node.path))
    for node in ordered:
        parent = node.dag_parent if node.dag_parent in nodes else None
        parent_side = source_side.get(parent, FitBuildSide.MIDDLE)
        side = parent_side
        if side is FitBuildSide.MIDDLE:
            if node.world_position[0] < -center_tolerance:
                side = FitBuildSide.RIGHT
            elif node.world_position[0] > center_tolerance:
                side = FitBuildSide.LEFT
        source_side[node.path] = side

        item = metadata_by_joint[node.path]
        no_mirror = inherited_no_mirror.get(parent, False) or item.no_mirror
        left_only = inherited_left_only.get(parent, False) or item.no_mirror_left
        inherited_no_mirror[node.path] = no_mirror
        inherited_left_only[node.path] = left_only

        if side is FitBuildSide.LEFT and not no_mirror:
            raise FitSymmetryValidationError(
                f"{node.short_name} 从 Left 侧开始；可镜像分支必须从 Right 侧开始"
            )
        if side is FitBuildSide.LEFT and not left_only:
            raise FitSymmetryValidationError(
                f"{node.short_name} 位于 Left 侧时必须显式启用 Left-only 规则"
            )

        if side is FitBuildSide.MIDDLE:
            target_sides = (FitBuildSide.MIDDLE,)
        elif no_mirror:
            target_sides = (
                (FitBuildSide.LEFT,) if left_only else (FitBuildSide.RIGHT,)
            )
        else:
            target_sides = (FitBuildSide.RIGHT, FitBuildSide.LEFT)

        for target_side in target_sides:
            mirrored = (
                side is FitBuildSide.RIGHT and target_side is FitBuildSide.LEFT
            )
            position = node.world_position
            if mirrored:
                position = (-position[0], position[1], position[2])
            parent_output = None
            if parent is not None:
                parent_target_side = target_side
                if source_side[parent] is FitBuildSide.MIDDLE:
                    parent_target_side = FitBuildSide.MIDDLE
                parent_output = output_paths[(parent, parent_target_side)]
            output_name = f"{node.short_name}_{target_side.value}"
            output_path = (
                f"{parent_output}|{output_name}"
                if parent_output is not None
                else f"|{output_name}"
            )
            output_paths[(node.path, target_side)] = output_path
            instances.append(
                FitSymmetryInstance(
                    source_joint=node.path,
                    output_path=output_path,
                    output_name=output_name,
                    parent_output_path=parent_output,
                    side=target_side,
                    world_position=position,
                    mirrored=mirrored,
                )
            )
    return tuple(instances)
