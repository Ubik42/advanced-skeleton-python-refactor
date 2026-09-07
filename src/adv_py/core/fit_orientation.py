from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite, sqrt

from .fit_container import FitUpAxis
from .fit_hierarchy import (
    TRANSLATION_AXES,
    FitHierarchyNode,
    FitHierarchySnapshot,
    audit_fit_hierarchy,
)
from .fit_metadata import FitJointMetadata


Vector3 = tuple[float, float, float]
IDENTITY_AXES: tuple[Vector3, Vector3, Vector3] = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)


class FitOrientationValidationError(ValueError):
    """Raised when a joint chain cannot be oriented without unsafe changes."""


class FitWorldAxis(str, Enum):
    X = "x"
    Y = "y"
    Z = "z"


class FitLocalDirection(str, Enum):
    POSITIVE_X = "+x"
    POSITIVE_Y = "+y"
    POSITIVE_Z = "+z"
    NEGATIVE_X = "-x"
    NEGATIVE_Y = "-y"
    NEGATIVE_Z = "-z"

    @property
    def unsigned_axis(self) -> FitWorldAxis:
        return FitWorldAxis(self.value[-1])


@dataclass(frozen=True, slots=True)
class FitWorldOrientationPolicy:
    """Local axes requested to face world up and forward directions."""

    up_local_direction: FitLocalDirection
    forward_local_direction: FitLocalDirection | None


@dataclass(frozen=True, slots=True)
class FitOrientationAxisConfiguration:
    primary: FitLocalDirection = FitLocalDirection.POSITIVE_X
    secondary: FitLocalDirection = FitLocalDirection.POSITIVE_Y
    world_match: bool = False

    def __post_init__(self) -> None:
        if self.primary.unsigned_axis is self.secondary.unsigned_axis:
            raise FitOrientationValidationError(
                "FitSkeleton primaryAxis 与 secondaryAxis 不能使用同一本地轴"
            )


def parse_fit_axis_direction(
    value: str,
    *,
    field: str,
) -> FitLocalDirection:
    values = {
        "X": FitLocalDirection.POSITIVE_X,
        "Y": FitLocalDirection.POSITIVE_Y,
        "Z": FitLocalDirection.POSITIVE_Z,
        "-X": FitLocalDirection.NEGATIVE_X,
        "-Y": FitLocalDirection.NEGATIVE_Y,
        "-Z": FitLocalDirection.NEGATIVE_Z,
    }
    try:
        return values[value]
    except KeyError as error:
        raise FitOrientationValidationError(
            f"{field} 不是受支持的轴方向：{value}"
        ) from error


def parse_world_orientation_policy(
    world_orient_up: str | None,
    world_orient_forward: str | None,
    *,
    joint: str = "Fit joint",
) -> FitWorldOrientationPolicy | None:
    if world_orient_up is None:
        if world_orient_forward is not None:
            raise FitOrientationValidationError(
                f"{joint} 设置了 worldOrientForward，但缺少 worldOrientUp"
            )
        return None

    up_values = {
        "xUp": FitLocalDirection.POSITIVE_X,
        "yUp": FitLocalDirection.POSITIVE_Y,
        "zUp": FitLocalDirection.POSITIVE_Z,
        "xDown": FitLocalDirection.NEGATIVE_X,
        "yDown": FitLocalDirection.NEGATIVE_Y,
        "zDown": FitLocalDirection.NEGATIVE_Z,
    }
    forward_values = {
        "xForward": FitLocalDirection.POSITIVE_X,
        "yForward": FitLocalDirection.POSITIVE_Y,
        "zForward": FitLocalDirection.POSITIVE_Z,
        "xBackward": FitLocalDirection.NEGATIVE_X,
        "yBackward": FitLocalDirection.NEGATIVE_Y,
        "zBackward": FitLocalDirection.NEGATIVE_Z,
    }
    try:
        up = up_values[world_orient_up]
    except KeyError as error:
        raise FitOrientationValidationError(
            f"{joint} 的 worldOrientUp 值无效：{world_orient_up}"
        ) from error
    if world_orient_forward in (None, "free"):
        return FitWorldOrientationPolicy(up, None)
    try:
        forward = forward_values[world_orient_forward]
    except KeyError as error:
        raise FitOrientationValidationError(
            f"{joint} 的 worldOrientForward 值无效：{world_orient_forward}"
        ) from error
    if forward.unsigned_axis is up.unsigned_axis:
        raise FitOrientationValidationError(
            f"{joint} 的 worldOrientUp 与 worldOrientForward 不能使用同一本地轴"
        )
    return FitWorldOrientationPolicy(up, forward)


@dataclass(frozen=True, slots=True)
class FitJointOrientationState:
    joint: str
    joint_orient: Vector3
    rotation: Vector3
    world_axes: tuple[Vector3, Vector3, Vector3]
    writable_joint_orient_axes: frozenset[str] = TRANSLATION_AXES


@dataclass(frozen=True, slots=True)
class FitOrientationSnapshot:
    hierarchy: FitHierarchySnapshot
    up_axis: FitUpAxis
    joints: tuple[FitJointOrientationState, ...]
    metadata: tuple[FitJointMetadata, ...] = ()
    axis_configuration: FitOrientationAxisConfiguration = (
        FitOrientationAxisConfiguration()
    )


@dataclass(frozen=True, slots=True)
class FitOrientationChildSelection:
    joint: str
    child: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.joint, str)
            or not self.joint.strip()
            or not isinstance(self.child, str)
            or not self.child.strip()
        ):
            raise FitOrientationValidationError("分支朝向的关节和子级名称不能为空")


@dataclass(frozen=True, slots=True)
class FitOrientationRequest:
    joints: tuple[str, ...]
    child_selections: tuple[FitOrientationChildSelection, ...] = ()

    def __post_init__(self) -> None:
        if not self.joints:
            raise FitOrientationValidationError("至少需要一个朝向目标关节")
        if any(not isinstance(name, str) or not name.strip() for name in self.joints):
            raise FitOrientationValidationError("朝向目标关节名称不能为空")
        if len(self.joints) != len(set(self.joints)):
            raise FitOrientationValidationError("朝向目标关节不能重复")
        selection_joints = tuple(item.joint for item in self.child_selections)
        if len(selection_joints) != len(set(selection_joints)):
            raise FitOrientationValidationError("同一分支朝向目标不能重复指定子级")


@dataclass(frozen=True, slots=True)
class FitOrientationChange:
    joint: str
    child: str
    before_joint_orient: Vector3
    preserved_child_joint_orients: tuple[tuple[str, Vector3], ...]
    descendant_world_positions: tuple[tuple[str, Vector3], ...]
    desired_primary_world: Vector3
    desired_secondary_world: Vector3
    secondary_world_axis: FitWorldAxis


@dataclass(frozen=True, slots=True)
class FitWorldOrientationChange:
    joint: str
    child: str
    before_joint_orient: Vector3
    preserved_child_joint_orients: tuple[tuple[str, Vector3], ...]
    descendant_world_positions: tuple[tuple[str, Vector3], ...]
    desired_world_axes: tuple[Vector3, Vector3, Vector3]
    policy: FitWorldOrientationPolicy


def world_axes_from_orientation_policy(
    policy: FitWorldOrientationPolicy,
    *,
    free_secondary_local: FitLocalDirection | None = None,
    free_secondary_world: Vector3 | None = None,
) -> tuple[Vector3, Vector3, Vector3]:
    axes: dict[FitWorldAxis, Vector3] = {}
    axes[policy.up_local_direction.unsigned_axis] = _signed_world_direction(
        policy.up_local_direction,
        (0.0, 1.0, 0.0),
    )
    if policy.forward_local_direction is None:
        if free_secondary_local is None or free_secondary_world is None:
            raise FitOrientationValidationError(
                "自由 Forward 需要 secondaryAxis 和水平参考方向"
            )
        reference_local = free_secondary_local
        reference_world = _normalize(
            free_secondary_world,
            "自由 Forward 的水平参考方向无效",
        )
    else:
        reference_local = policy.forward_local_direction
        reference_world = (0.0, 0.0, 1.0)
    if reference_local.unsigned_axis is policy.up_local_direction.unsigned_axis:
        raise FitOrientationValidationError(
            "worldOrient Up 与 secondary 不能使用同一本地轴"
        )
    axes[reference_local.unsigned_axis] = _signed_world_direction(
        reference_local,
        reference_world,
    )
    if FitWorldAxis.X not in axes:
        axes[FitWorldAxis.X] = _cross(axes[FitWorldAxis.Y], axes[FitWorldAxis.Z])
    elif FitWorldAxis.Y not in axes:
        axes[FitWorldAxis.Y] = _cross(axes[FitWorldAxis.Z], axes[FitWorldAxis.X])
    else:
        axes[FitWorldAxis.Z] = _cross(axes[FitWorldAxis.X], axes[FitWorldAxis.Y])
    return (axes[FitWorldAxis.X], axes[FitWorldAxis.Y], axes[FitWorldAxis.Z])


def plan_world_fit_orientations(
    snapshot: FitOrientationSnapshot,
    request: FitOrientationRequest,
    *,
    tolerance: float = 1e-5,
) -> tuple[FitWorldOrientationChange, ...]:
    _validate_orientation_snapshot(snapshot, tolerance)
    if request.child_selections:
        raise FitOrientationValidationError(
            "worldOrient 写入器当前不接受分支子级选择"
        )
    if snapshot.up_axis is not FitUpAxis.Y:
        raise FitOrientationValidationError(
            "worldOrient 当前只支持 Maya Y-Up 场景"
        )
    if snapshot.axis_configuration.world_match:
        raise FitOrientationValidationError(
            "World Match 已启用；当前 worldOrient 写入器不处理该分支"
        )

    hierarchy = {node.path: node for node in snapshot.hierarchy.joints}
    orientations = {state.joint: state for state in snapshot.joints}
    metadata = {item.joint: item for item in snapshot.metadata}
    if not snapshot.metadata or set(metadata) != set(hierarchy):
        raise FitOrientationValidationError("worldOrient 计划需要完整的 Fit joint 元数据")
    children = _joint_children(snapshot.hierarchy)
    resolved = _resolve_orientation_targets(snapshot.hierarchy, request)

    changes: list[FitWorldOrientationChange] = []
    for path in sorted(resolved, key=lambda item: (item.count("|"), item)):
        node = hierarchy[path]
        state = orientations[path]
        policy = parse_world_orientation_policy(
            metadata[path].world_orient_up,
            metadata[path].world_orient_forward,
            joint=node.short_name,
        )
        if policy is None:
            raise FitOrientationValidationError(
                f"{node.short_name} 没有 worldOrient 策略"
            )
        direct_children = children[path]
        if len(direct_children) != 1:
            raise FitOrientationValidationError(
                f"{node.short_name} 必须有且只有一个直接 joint 子级"
            )
        _validate_orientation_target(
            snapshot,
            path,
            direct_children[0],
            tolerance=tolerance,
        )
        if policy.forward_local_direction is None:
            child_position = hierarchy[direct_children[0]].world_position
            direction = _subtract(child_position, node.world_position)
            horizontal = (direction[0], 0.0, direction[2])
            desired = world_axes_from_orientation_policy(
                policy,
                free_secondary_local=snapshot.axis_configuration.secondary,
                free_secondary_world=horizontal,
            )
        else:
            desired = world_axes_from_orientation_policy(policy)
        if all(
            _dot(_normalize(current, "当前世界轴无效"), wanted)
            >= 1.0 - tolerance
            for current, wanted in zip(state.world_axes, desired)
        ):
            continue
        child_path = direct_children[0]
        descendant_paths = _descendant_paths(hierarchy, path)
        changes.append(
            FitWorldOrientationChange(
                joint=path,
                child=child_path,
                before_joint_orient=state.joint_orient,
                preserved_child_joint_orients=(
                    (child_path, orientations[child_path].joint_orient),
                ),
                descendant_world_positions=tuple(
                    (descendant, hierarchy[descendant].world_position)
                    for descendant in descendant_paths
                ),
                desired_world_axes=desired,
                policy=policy,
            )
        )
    return tuple(changes)


def plan_simple_fit_orientations(
    snapshot: FitOrientationSnapshot,
    request: FitOrientationRequest,
    *,
    tolerance: float = 1e-5,
) -> tuple[FitOrientationChange, ...]:
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not isfinite(float(tolerance))
        or tolerance <= 0
    ):
        raise FitOrientationValidationError("朝向比较容差必须是正有限数值")
    hierarchy_issues = audit_fit_hierarchy(snapshot.hierarchy)
    if hierarchy_issues:
        raise FitOrientationValidationError(
            "FitSkeleton 层级无效："
            + "；".join(issue.message for issue in hierarchy_issues)
        )
    hierarchy = {node.path: node for node in snapshot.hierarchy.joints}
    by_name = {node.short_name: node for node in snapshot.hierarchy.joints}
    orientations = {state.joint: state for state in snapshot.joints}
    if len(orientations) != len(snapshot.joints) or set(orientations) != set(
        hierarchy
    ):
        raise FitOrientationValidationError("朝向快照与 FitSkeleton 层级不一致")
    metadata = {item.joint: item for item in snapshot.metadata}
    if snapshot.metadata and (
        len(metadata) != len(snapshot.metadata) or set(metadata) != set(hierarchy)
    ):
        raise FitOrientationValidationError("朝向元数据与 FitSkeleton 层级不一致")

    children = _joint_children(snapshot.hierarchy)

    resolved: list[str] = []
    for name in request.joints:
        node = hierarchy.get(name) or by_name.get(name)
        if node is None:
            raise FitOrientationValidationError(f"朝向目标不在 FitSkeleton 中：{name}")
        if node.path in resolved:
            raise FitOrientationValidationError(
                f"多个朝向目标解析到同一关节：{node.path}"
            )
        resolved.append(node.path)
    child_selections = _resolve_child_selections(
        snapshot.hierarchy,
        request,
        frozenset(resolved),
    )

    changes: list[FitOrientationChange] = []
    for path in sorted(resolved, key=lambda item: (item.count("|"), item)):
        state = orientations[path]
        item_metadata = metadata.get(path)
        if item_metadata is not None:
            policy = parse_world_orientation_policy(
                item_metadata.world_orient_up,
                item_metadata.world_orient_forward,
                joint=hierarchy[path].short_name,
            )
            if policy is not None:
                raise FitOrientationValidationError(
                    f"{hierarchy[path].short_name} 使用 worldOrient 策略 "
                    f"({policy.up_local_direction.value}, "
                    f"{policy.forward_local_direction.value if policy.forward_local_direction else 'free'})；"
                    "当前单子链写入器尚不支持该策略"
                )
        direct_children = children[path]
        if not direct_children:
            raise FitOrientationValidationError(
                f"{hierarchy[path].short_name} 必须至少有一个直接 joint 子级"
            )
        child_path = child_selections.get(path)
        if len(direct_children) > 1 and child_path is None:
            raise FitOrientationValidationError(
                f"{hierarchy[path].short_name} 有多个直接 joint 子级，"
                "必须显式指定朝向子级"
            )
        if child_path is None:
            child_path = direct_children[0]
        if any(abs(value) > tolerance for value in state.rotation):
            raise FitOrientationValidationError(
                f"{hierarchy[path].short_name} 的 rotate 必须先归零"
            )
        if state.writable_joint_orient_axes != TRANSLATION_AXES:
            raise FitOrientationValidationError(
                f"{hierarchy[path].short_name} 的 jointOrient 不可完整写入"
            )

        child = hierarchy[child_path]
        descendant_paths = tuple(
            item
            for item in sorted(hierarchy, key=lambda value: (value.count("|"), value))
            if item.startswith(path + "|")
        )
        for descendant_path in descendant_paths:
            descendant = hierarchy[descendant_path]
            if descendant.writable_translation_axes != TRANSLATION_AXES:
                raise FitOrientationValidationError(
                    f"{descendant.short_name} 的 translate 无法用于朝向补偿"
                )
        for direct_child_path in direct_children:
            direct_child = hierarchy[direct_child_path]
            if (
                orientations[direct_child_path].writable_joint_orient_axes
                != TRANSLATION_AXES
            ):
                raise FitOrientationValidationError(
                    f"{direct_child.short_name} 的 jointOrient 无法恢复"
                )
        primary = _normalize(
            _subtract(child.world_position, hierarchy[path].world_position),
            f"{hierarchy[path].short_name} 与子级位置重合",
        )
        secondary_axis, reference = _secondary_reference(snapshot.up_axis, primary)
        secondary = _normalize(
            _subtract(reference, _scale(primary, _dot(reference, primary))),
            "无法建立稳定的 secondary axis",
        )
        if (
            _dot(_normalize(state.world_axes[0], "当前 X 轴无效"), primary)
            >= 1.0 - tolerance
            and _dot(_normalize(state.world_axes[1], "当前 Y 轴无效"), secondary)
            >= 1.0 - tolerance
        ):
            continue
        changes.append(
            FitOrientationChange(
                joint=path,
                child=child_path,
                before_joint_orient=state.joint_orient,
                preserved_child_joint_orients=tuple(
                    (direct_child_path, orientations[direct_child_path].joint_orient)
                    for direct_child_path in direct_children
                ),
                descendant_world_positions=tuple(
                    (descendant_path, hierarchy[descendant_path].world_position)
                    for descendant_path in descendant_paths
                ),
                desired_primary_world=primary,
                desired_secondary_world=secondary,
                secondary_world_axis=secondary_axis,
            )
        )
    return tuple(changes)


def orientation_matches(
    change: FitOrientationChange,
    state: FitJointOrientationState,
    *,
    tolerance: float = 1e-4,
) -> bool:
    primary = _normalize(state.world_axes[0], "复检 X 轴无效")
    secondary = _normalize(state.world_axes[1], "复检 Y 轴无效")
    return (
        _dot(primary, change.desired_primary_world) >= 1.0 - tolerance
        and _dot(secondary, change.desired_secondary_world) >= 1.0 - tolerance
        and all(abs(value) <= tolerance for value in state.rotation)
    )


def world_orientation_matches(
    change: FitWorldOrientationChange,
    state: FitJointOrientationState,
    *,
    tolerance: float = 1e-4,
) -> bool:
    return all(
        _dot(_normalize(current, "复检世界轴无效"), wanted) >= 1.0 - tolerance
        for current, wanted in zip(state.world_axes, change.desired_world_axes)
    ) and all(abs(value) <= tolerance for value in state.rotation)


def _validate_orientation_snapshot(
    snapshot: FitOrientationSnapshot,
    tolerance: float,
) -> None:
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not isfinite(float(tolerance))
        or tolerance <= 0
    ):
        raise FitOrientationValidationError("朝向比较容差必须是正有限数值")
    issues = audit_fit_hierarchy(snapshot.hierarchy)
    if issues:
        raise FitOrientationValidationError(
            "FitSkeleton 层级无效：" + "；".join(item.message for item in issues)
        )
    hierarchy = {node.path for node in snapshot.hierarchy.joints}
    orientations = {state.joint for state in snapshot.joints}
    if len(orientations) != len(snapshot.joints) or orientations != hierarchy:
        raise FitOrientationValidationError("朝向快照与 FitSkeleton 层级不一致")
    metadata = {item.joint for item in snapshot.metadata}
    if snapshot.metadata and (
        len(metadata) != len(snapshot.metadata) or metadata != hierarchy
    ):
        raise FitOrientationValidationError("朝向元数据与 FitSkeleton 层级不一致")


def _joint_children(snapshot: FitHierarchySnapshot) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {node.path: [] for node in snapshot.joints}
    for node in snapshot.joints:
        if node.dag_parent in children:
            children[node.dag_parent].append(node.path)
    for paths in children.values():
        paths.sort()
    return children


def _resolve_orientation_targets(
    snapshot: FitHierarchySnapshot,
    request: FitOrientationRequest,
) -> tuple[str, ...]:
    hierarchy = {node.path: node for node in snapshot.joints}
    by_name = {node.short_name: node for node in snapshot.joints}
    resolved: list[str] = []
    for name in request.joints:
        node = hierarchy.get(name) or by_name.get(name)
        if node is None:
            raise FitOrientationValidationError(
                f"朝向目标不在 FitSkeleton 中：{name}"
            )
        if node.path in resolved:
            raise FitOrientationValidationError(
                f"多个朝向目标解析到同一关节：{node.path}"
            )
        resolved.append(node.path)
    return tuple(resolved)


def _resolve_child_selections(
    snapshot: FitHierarchySnapshot,
    request: FitOrientationRequest,
    requested_paths: frozenset[str],
) -> dict[str, str]:
    hierarchy = {node.path: node for node in snapshot.joints}
    by_name = {node.short_name: node for node in snapshot.joints}
    resolved: dict[str, str] = {}
    for selection in request.child_selections:
        parent = hierarchy.get(selection.joint) or by_name.get(selection.joint)
        if parent is None:
            raise FitOrientationValidationError(
                f"分支朝向父关节不在 FitSkeleton 中：{selection.joint}"
            )
        child = hierarchy.get(selection.child) or by_name.get(selection.child)
        if child is None:
            raise FitOrientationValidationError(
                f"分支朝向子关节不在 FitSkeleton 中：{selection.child}"
            )
        if parent.path not in requested_paths:
            raise FitOrientationValidationError(
                f"分支选择的父关节未包含在朝向目标中：{parent.short_name}"
            )
        if parent.path in resolved:
            raise FitOrientationValidationError(
                f"同一分支朝向目标解析出多个子级：{parent.short_name}"
            )
        if child.dag_parent != parent.path:
            raise FitOrientationValidationError(
                f"{child.short_name} 不是 {parent.short_name} 的直接 joint 子级"
            )
        resolved[parent.path] = child.path
    return resolved


def _descendant_paths(
    hierarchy: dict[str, FitHierarchyNode],
    path: str,
) -> tuple[str, ...]:
    return tuple(
        item
        for item in sorted(hierarchy, key=lambda value: (value.count("|"), value))
        if item.startswith(path + "|")
    )


def _validate_orientation_target(
    snapshot: FitOrientationSnapshot,
    path: str,
    child_path: str,
    *,
    tolerance: float,
) -> None:
    hierarchy = {node.path: node for node in snapshot.hierarchy.joints}
    orientations = {state.joint: state for state in snapshot.joints}
    node = hierarchy[path]
    state = orientations[path]
    if any(abs(value) > tolerance for value in state.rotation):
        raise FitOrientationValidationError(
            f"{node.short_name} 的 rotate 必须先归零"
        )
    if state.writable_joint_orient_axes != TRANSLATION_AXES:
        raise FitOrientationValidationError(
            f"{node.short_name} 的 jointOrient 不可完整写入"
        )
    for descendant_path in _descendant_paths(hierarchy, path):
        descendant = hierarchy[descendant_path]
        if descendant.writable_translation_axes != TRANSLATION_AXES:
            raise FitOrientationValidationError(
                f"{descendant.short_name} 的 translate 无法用于朝向补偿"
            )
    child = hierarchy[child_path]
    if orientations[child_path].writable_joint_orient_axes != TRANSLATION_AXES:
        raise FitOrientationValidationError(
            f"{child.short_name} 的 jointOrient 无法恢复"
        )


def _secondary_reference(
    up_axis: FitUpAxis,
    primary: Vector3,
) -> tuple[FitWorldAxis, Vector3]:
    preferred = FitWorldAxis.Y if up_axis is FitUpAxis.Y else FitWorldAxis.Z
    candidates = (preferred, FitWorldAxis.Z, FitWorldAxis.Y, FitWorldAxis.X)
    vectors = {
        FitWorldAxis.X: (1.0, 0.0, 0.0),
        FitWorldAxis.Y: (0.0, 1.0, 0.0),
        FitWorldAxis.Z: (0.0, 0.0, 1.0),
    }
    for axis in dict.fromkeys(candidates):
        if abs(_dot(primary, vectors[axis])) < 0.95:
            return axis, vectors[axis]
    raise FitOrientationValidationError("无法选择 secondary world axis")


def _subtract(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(value: Vector3, factor: float) -> Vector3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _signed_world_direction(
    local_direction: FitLocalDirection,
    world_direction: Vector3,
) -> Vector3:
    factor = -1.0 if local_direction.value.startswith("-") else 1.0
    return _scale(world_direction, factor)


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normalize(value: Vector3, error_message: str) -> Vector3:
    length = sqrt(_dot(value, value))
    if length <= 1e-10:
        raise FitOrientationValidationError(error_message)
    return (value[0] / length, value[1] / length, value[2] / length)
