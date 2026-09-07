from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite, sqrt

from .fit_container import FitUpAxis
from .fit_hierarchy import (
    TRANSLATION_AXES,
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


@dataclass(frozen=True, slots=True)
class FitOrientationRequest:
    joints: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.joints:
            raise FitOrientationValidationError("至少需要一个朝向目标关节")
        if any(not isinstance(name, str) or not name.strip() for name in self.joints):
            raise FitOrientationValidationError("朝向目标关节名称不能为空")
        if len(self.joints) != len(set(self.joints)):
            raise FitOrientationValidationError("朝向目标关节不能重复")


@dataclass(frozen=True, slots=True)
class FitOrientationChange:
    joint: str
    child: str
    before_joint_orient: Vector3
    child_before_joint_orient: Vector3
    descendant_world_positions: tuple[tuple[str, Vector3], ...]
    desired_primary_world: Vector3
    desired_secondary_world: Vector3
    secondary_world_axis: FitWorldAxis


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

    children: dict[str, list[str]] = {path: [] for path in hierarchy}
    for node in snapshot.hierarchy.joints:
        if node.dag_parent in children:
            children[node.dag_parent].append(node.path)

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
        if len(direct_children) != 1:
            raise FitOrientationValidationError(
                f"{hierarchy[path].short_name} 必须有且只有一个直接 joint 子级"
            )
        if any(abs(value) > tolerance for value in state.rotation):
            raise FitOrientationValidationError(
                f"{hierarchy[path].short_name} 的 rotate 必须先归零"
            )
        if state.writable_joint_orient_axes != TRANSLATION_AXES:
            raise FitOrientationValidationError(
                f"{hierarchy[path].short_name} 的 jointOrient 不可完整写入"
            )

        child_path = direct_children[0]
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
        child_orientation = orientations[child_path]
        if child_orientation.writable_joint_orient_axes != TRANSLATION_AXES:
            raise FitOrientationValidationError(
                f"{child.short_name} 的 jointOrient 无法恢复"
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
                child_before_joint_orient=child_orientation.joint_orient,
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


def _dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normalize(value: Vector3, error_message: str) -> Vector3:
    length = sqrt(_dot(value, value))
    if length <= 1e-10:
        raise FitOrientationValidationError(error_message)
    return (value[0] / length, value[1] / length, value[2] / length)
