from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

from .body_arm_blend import BodyArmBlendPlan
from .body_arm_ik import BodyArmIkPlan, solve_arm_pole_position
from .body_controls import BodyArmFkControlPlan
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class BodyArmFkToIkPlan:
    side: FitBuildSide
    blend_plug: str
    wrist_control_path: str
    pole_control_path: str
    wrist_position: Vector3
    wrist_axes: AxisFrame
    pole_position: Vector3
    body_joint_paths: tuple[str, str, str]
    body_joint_positions: tuple[Vector3, Vector3, Vector3]
    required_paths: tuple[str, ...]
    required_writable_plugs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodyArmFkToIkSceneState:
    existing_paths: tuple[str, ...]
    writable_plugs: tuple[str, ...]
    blend_value: float


@dataclass(frozen=True, slots=True)
class BodyArmIkToFkPlan:
    side: FitBuildSide
    blend_plug: str
    fk_control_paths: tuple[str, str, str]
    fk_control_axes: tuple[AxisFrame, AxisFrame, AxisFrame]
    fk_segment_plugs: tuple[str, str]
    fk_segment_translations: tuple[float, float]
    body_joint_paths: tuple[str, str, str]
    body_joint_positions: tuple[Vector3, Vector3, Vector3]
    body_joint_axes: tuple[AxisFrame, AxisFrame, AxisFrame]
    required_paths: tuple[str, ...]
    required_writable_plugs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodyArmIkToFkSceneState:
    existing_paths: tuple[str, ...]
    writable_plugs: tuple[str, ...]
    blend_value: float
    body_joint_positions: tuple[Vector3, Vector3, Vector3]
    body_joint_axes: tuple[AxisFrame, AxisFrame, AxisFrame]
    fk_segment_translations: tuple[float, float]


@dataclass(frozen=True, slots=True)
class BodyArmMatchIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_arm_fk_to_ik(
    body: BodySkeletonSnapshot,
    ik: BodyArmIkPlan,
    blend: BodyArmBlendPlan,
    side: FitBuildSide,
    *,
    pole_distance_scale: float = 0.75,
) -> BodyArmFkToIkPlan:
    if side not in (FitBuildSide.RIGHT, FitBuildSide.LEFT):
        raise ValueError("Arm FK→IK 匹配只接受 Left 或 Right")
    limbs = tuple(spec for spec in ik.limbs if spec.side is side)
    blend_sides = tuple(spec for spec in blend.sides if spec.side is side)
    if len(limbs) != 1 or len(blend_sides) != 1:
        raise ValueError("Arm FK→IK 匹配要求唯一的目标侧")
    limb, blend_side = limbs[0], blend_sides[0]
    by_path = {joint.path: joint for joint in body.joints}
    paths = tuple(joint.body_joint for joint in blend_side.joints)
    if len(paths) != 3 or any(path not in by_path for path in paths):
        raise ValueError("Arm FK→IK 匹配要求完整的 Shoulder/Elbow/Wrist Body 链")
    joints = tuple(by_path[path] for path in paths)
    pole = solve_arm_pole_position(
        joints[0].world_position,
        joints[1].world_position,
        joints[2].world_position,
        joints[1].world_axes[2],
        distance_scale=pole_distance_scale,
    )
    blend_plug = f"{blend.settings_path}.{blend_side.attribute}"
    writable = tuple(
        f"{path}.{channel}"
        for path, channels in (
            (limb.wrist_control_path, ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ")),
            (limb.pole_control_path, ("translateX", "translateY", "translateZ")),
        )
        for channel in channels
    ) + (blend_plug,)
    return BodyArmFkToIkPlan(
        side,
        blend_plug,
        limb.wrist_control_path,
        limb.pole_control_path,
        joints[2].world_position,
        joints[2].world_axes,
        pole,
        paths,
        tuple(joint.world_position for joint in joints),
        (limb.wrist_control_path, limb.pole_control_path, *paths),
        writable,
    )


def audit_body_arm_fk_to_ik_preflight(
    plan: BodyArmFkToIkPlan,
    state: BodyArmFkToIkSceneState,
    *,
    tolerance: float = 1e-6,
) -> tuple[BodyArmMatchIssue, ...]:
    issues = []
    missing_paths = tuple(sorted(set(plan.required_paths) - set(state.existing_paths)))
    if missing_paths:
        issues.append(BodyArmMatchIssue("missing_paths", "Arm FK→IK 匹配节点缺失", "、".join(missing_paths)))
    locked = tuple(sorted(set(plan.required_writable_plugs) - set(state.writable_plugs)))
    if locked:
        issues.append(BodyArmMatchIssue("unwritable_channels", "Arm FK→IK 匹配通道不可写", "、".join(locked)))
    if abs(state.blend_value) > tolerance:
        issues.append(BodyArmMatchIssue("not_in_fk_mode", "目标手臂当前不是 FK 模式", plan.side.value))
    return tuple(issues)


def plan_body_arm_ik_to_fk(
    body: BodySkeletonSnapshot,
    fk_controls: BodyArmFkControlPlan,
    blend: BodyArmBlendPlan,
    side: FitBuildSide,
) -> BodyArmIkToFkPlan:
    if side not in (FitBuildSide.RIGHT, FitBuildSide.LEFT):
        raise ValueError("Arm IK→FK 匹配只接受 Left 或 Right")
    controls = tuple(spec for spec in fk_controls.controls if spec.side is side)
    blend_sides = tuple(spec for spec in blend.sides if spec.side is side)
    if len(controls) != 3 or len(blend_sides) != 1:
        raise ValueError("Arm IK→FK 匹配要求唯一的三层 FK 控制链")
    by_path = {joint.path: joint for joint in body.joints}
    paths = tuple(joint.body_joint for joint in blend_sides[0].joints)
    if len(paths) != 3 or any(path not in by_path for path in paths):
        raise ValueError("Arm IK→FK 匹配要求完整的 Shoulder/Elbow/Wrist Body 链")
    joints = tuple(by_path[path] for path in paths)
    control_paths = tuple(control.control_path for control in controls)
    driver_paths = tuple(control.driven_joint for control in controls)
    segment_plugs = tuple(f"{path}.translateX" for path in driver_paths[1:])
    segment_translations = tuple(
        _signed_local_x_distance(parent, child)
        for parent, child in zip(joints, joints[1:])
    )
    blend_plug = f"{blend.settings_path}.{blend_sides[0].attribute}"
    writable = (
        tuple(f"{path}.rotate{axis}" for path in control_paths for axis in "XYZ")
        + segment_plugs
        + (blend_plug,)
    )
    return BodyArmIkToFkPlan(
        side,
        blend_plug,
        control_paths,
        tuple(joint.world_axes for joint in joints),
        segment_plugs,
        segment_translations,
        paths,
        tuple(joint.world_position for joint in joints),
        tuple(joint.world_axes for joint in joints),
        (*control_paths, *driver_paths, *paths),
        writable,
    )


def audit_body_arm_ik_to_fk_preflight(
    plan: BodyArmIkToFkPlan,
    state: BodyArmIkToFkSceneState,
    *,
    tolerance: float = 1e-6,
) -> tuple[BodyArmMatchIssue, ...]:
    issues = []
    missing_paths = tuple(sorted(set(plan.required_paths) - set(state.existing_paths)))
    if missing_paths:
        issues.append(BodyArmMatchIssue("missing_paths", "Arm IK→FK 匹配节点缺失", "、".join(missing_paths)))
    locked = tuple(sorted(set(plan.required_writable_plugs) - set(state.writable_plugs)))
    if locked:
        issues.append(BodyArmMatchIssue("unwritable_channels", "Arm IK→FK 匹配通道不可写", "、".join(locked)))
    if abs(state.blend_value - 1.0) > tolerance:
        issues.append(BodyArmMatchIssue("not_in_ik_mode", "目标手臂当前不是 IK 模式", plan.side.value))
    if len(state.body_joint_positions) != len(plan.body_joint_positions) or any(
        not _close(actual, expected, tolerance)
        for actual, expected in zip(
            state.body_joint_positions,
            plan.body_joint_positions,
        )
    ) or len(state.body_joint_axes) != len(plan.body_joint_axes) or any(
        not _axis_frame_close(actual, expected, tolerance)
        for actual, expected in zip(state.body_joint_axes, plan.body_joint_axes)
    ):
        issues.append(BodyArmMatchIssue("pose_drift", "Arm IK→FK 匹配姿态已变化", plan.side.value))
    return tuple(issues)


def audit_body_arm_ik_to_fk_result(
    plan: BodyArmIkToFkPlan,
    body: BodySkeletonSnapshot,
    blend_value: float,
    fk_segment_translations: tuple[float, float],
    *,
    position_tolerance: float = 1e-3,
    axis_tolerance: float = 1e-3,
) -> tuple[BodyArmMatchIssue, ...]:
    issues = []
    if abs(blend_value) > 1e-6:
        issues.append(BodyArmMatchIssue("blend_not_fk", "Arm IK→FK 切换后 blend 未到 FK", plan.side.value))
    if len(fk_segment_translations) != len(plan.fk_segment_translations) or not _close(
        fk_segment_translations,
        plan.fk_segment_translations,
        position_tolerance,
    ):
        issues.append(BodyArmMatchIssue("segment_length_mismatch", "Arm IK→FK 切换后 FK 段长不一致", plan.side.value))
    by_path = {joint.path: joint for joint in body.joints}
    for path, expected_position, expected_axes in zip(plan.body_joint_paths, plan.body_joint_positions, plan.body_joint_axes):
        current = by_path.get(path)
        if current is None or not _close(current.world_position, expected_position, position_tolerance):
            issues.append(BodyArmMatchIssue("position_pop", "Arm IK→FK 切换后关节位置跳变", path))
        if current is None or any(not _close(actual, expected, axis_tolerance) for actual, expected in zip(current.world_axes, expected_axes)):
            issues.append(BodyArmMatchIssue("orientation_pop", "Arm IK→FK 切换后关节朝向跳变", path))
    return tuple(issues)


def audit_body_arm_fk_to_ik_result(
    plan: BodyArmFkToIkPlan,
    body: BodySkeletonSnapshot,
    blend_value: float,
    *,
    position_tolerance: float = 1e-3,
    axis_tolerance: float = 1e-3,
) -> tuple[BodyArmMatchIssue, ...]:
    issues = []
    if abs(blend_value - 1.0) > 1e-6:
        issues.append(BodyArmMatchIssue("blend_not_ik", "Arm FK→IK 切换后 blend 未到 IK", plan.side.value))
    by_path = {joint.path: joint for joint in body.joints}
    for path, expected in zip(plan.body_joint_paths, plan.body_joint_positions):
        current = by_path.get(path)
        if current is None or not _close(current.world_position, expected, position_tolerance):
            issues.append(BodyArmMatchIssue("position_pop", "Arm FK→IK 切换后关节位置跳变", path))
    wrist = by_path.get(plan.body_joint_paths[2])
    if wrist is None or any(not _close(actual, expected, axis_tolerance) for actual, expected in zip(wrist.world_axes, plan.wrist_axes)):
        issues.append(BodyArmMatchIssue("wrist_orientation_pop", "Arm FK→IK 切换后 Wrist 朝向跳变", plan.body_joint_paths[2]))
    return tuple(issues)


def _close(left, right, tolerance):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _axis_frame_close(left: AxisFrame, right: AxisFrame, tolerance: float) -> bool:
    return all(_close(actual, expected, tolerance) for actual, expected in zip(left, right))


def _signed_local_x_distance(parent, child, *, tolerance: float = 1e-3) -> float:
    delta = tuple(b - a for a, b in zip(parent.world_position, child.world_position))
    length = sqrt(sum(value * value for value in delta))
    projected = sum(value * axis for value, axis in zip(delta, parent.world_axes[0]))
    if (
        not isfinite(length)
        or not isfinite(projected)
        or length <= 1e-6
        or abs(abs(projected) - length) > tolerance
    ):
        raise ValueError("Arm IK→FK 匹配要求 Body 段沿父关节本地 X 对齐")
    scale=parent.world_scale[0]
    if not isfinite(scale) or scale<=1e-8:
        raise ValueError("Arm IK→FK 父级缩放无效")
    return projected/scale
