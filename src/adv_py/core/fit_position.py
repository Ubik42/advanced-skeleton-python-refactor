from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .fit_hierarchy import FitHierarchySnapshot, audit_fit_hierarchy


Vector3 = tuple[float, float, float]
_AXES = ("x", "y", "z")


class FitPositionValidationError(ValueError):
    """Raised when a Fit joint position patch cannot be applied safely."""


@dataclass(frozen=True, slots=True)
class FitJointPositionEdit:
    joint: str
    local_position: Vector3

    def __post_init__(self) -> None:
        if not isinstance(self.joint, str) or not self.joint.strip():
            raise FitPositionValidationError("Fit joint 名称不能为空")
        if len(self.local_position) != 3 or not all(
            isfinite(float(value)) for value in self.local_position
        ):
            raise FitPositionValidationError("Fit joint 位置必须是有限三维向量")


@dataclass(frozen=True, slots=True)
class FitJointPositionPatch:
    edits: tuple[FitJointPositionEdit, ...]

    def __post_init__(self) -> None:
        if not self.edits:
            raise FitPositionValidationError("Fit joint 位置变更不能为空")
        names = tuple(edit.joint for edit in self.edits)
        if len(names) != len(set(names)):
            raise FitPositionValidationError("Fit joint 位置变更不能包含重复目标")


@dataclass(frozen=True, slots=True)
class FitJointPositionChange:
    joint: str
    before: Vector3
    after: Vector3
    changed_axes: tuple[str, ...]


def plan_fit_joint_position_changes(
    snapshot: FitHierarchySnapshot,
    patch: FitJointPositionPatch,
    *,
    tolerance: float = 1e-6,
) -> tuple[FitJointPositionChange, ...]:
    hierarchy_issues = audit_fit_hierarchy(snapshot)
    if hierarchy_issues:
        raise FitPositionValidationError(
            "FitSkeleton 层级无效："
            + "；".join(issue.message for issue in hierarchy_issues)
        )
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not isfinite(float(tolerance))
        or tolerance < 0
    ):
        raise FitPositionValidationError("位置比较容差必须是非负有限数值")

    by_path = {node.path: node for node in snapshot.joints}
    by_name = {node.short_name: node for node in snapshot.joints}
    changes: list[FitJointPositionChange] = []
    resolved_paths: set[str] = set()
    for edit in patch.edits:
        node = by_path.get(edit.joint) or by_name.get(edit.joint)
        if node is None:
            raise FitPositionValidationError(f"Fit joint 不在目标层级中：{edit.joint}")
        if node.path in resolved_paths:
            raise FitPositionValidationError(
                f"多个位置变更解析到同一个 Fit joint：{node.path}"
            )
        resolved_paths.add(node.path)
        after = tuple(float(value) for value in edit.local_position)
        changed_axes = tuple(
            axis
            for axis, before_value, after_value in zip(
                _AXES,
                node.local_position,
                after,
            )
            if abs(before_value - after_value) > tolerance
        )
        blocked_axes = tuple(
            axis
            for axis in changed_axes
            if axis not in node.writable_translation_axes
        )
        if blocked_axes:
            locked = tuple(
                axis for axis in blocked_axes if axis in node.locked_translation_axes
            )
            reason = "锁定" if locked == blocked_axes else "不可写"
            raise FitPositionValidationError(
                f"{node.short_name} 的位置轴{reason}："
                + "、".join(blocked_axes)
            )
        if node.short_name == "Root" and abs(after[0]) > 0.01:
            raise FitPositionValidationError("Root 的本地 X 位置必须保持在中心容差内")
        if changed_axes:
            changes.append(
                FitJointPositionChange(
                    joint=node.path,
                    before=node.local_position,
                    after=after,
                    changed_axes=changed_axes,
                )
            )
    return tuple(changes)
