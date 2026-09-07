from __future__ import annotations

from dataclasses import dataclass

from .body_arm_blend import BodyArmBlendPlan
from .body_arm_ik import BodyArmIkPlan, solve_arm_pole_position
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
