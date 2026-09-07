from __future__ import annotations

from dataclasses import dataclass

from .body_leg_blend import BodyLegBlendPlan
from .body_leg_ik import BodyLegIkPlan
from .body_leg_controls import BodyLegFkControlPlan
from .body_limb_ik import solve_limb_pole_position
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class BodyLegFkToIkPlan:
    side: FitBuildSide
    blend_plug: str
    ankle_control_path: str
    pole_control_path: str
    ankle_position: Vector3
    ankle_axes: AxisFrame
    pole_position: Vector3
    body_joint_paths: tuple[str, str, str]
    body_joint_positions: tuple[Vector3, Vector3, Vector3]
    required_paths: tuple[str, ...]
    required_writable_plugs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodyLegFkToIkSceneState:
    existing_paths: tuple[str, ...]
    writable_plugs: tuple[str, ...]
    blend_value: float
    body_joint_positions: tuple[Vector3, ...]
    ankle_axes: tuple[Vector3, ...]


@dataclass(frozen=True, slots=True)
class BodyLegIkToFkPlan:
    side: FitBuildSide
    blend_plug: str
    fk_control_paths: tuple[str, str, str]
    fk_control_axes: tuple[AxisFrame, AxisFrame, AxisFrame]
    body_joint_paths: tuple[str, str, str]
    body_joint_positions: tuple[Vector3, Vector3, Vector3]
    body_joint_axes: tuple[AxisFrame, AxisFrame, AxisFrame]
    required_paths: tuple[str, ...]
    required_writable_plugs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodyLegIkToFkSceneState:
    existing_paths: tuple[str, ...]
    writable_plugs: tuple[str, ...]
    blend_value: float
    body_joint_positions: tuple[Vector3, ...]
    body_joint_axes: tuple[AxisFrame, ...]


@dataclass(frozen=True, slots=True)
class BodyLegMatchIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_leg_fk_to_ik(
    body: BodySkeletonSnapshot,
    ik: BodyLegIkPlan,
    blend: BodyLegBlendPlan,
    side: FitBuildSide,
    *,
    pole_distance_scale: float = 0.75,
) -> BodyLegFkToIkPlan:
    if side not in (FitBuildSide.RIGHT, FitBuildSide.LEFT):
        raise ValueError("Leg FK→IK 匹配只接受 Left 或 Right")
    limbs = tuple(spec for spec in ik.limbs if spec.side is side)
    blend_sides = tuple(spec for spec in blend.sides if spec.side is side)
    if len(limbs) != 1 or len(blend_sides) != 1:
        raise ValueError("Leg FK→IK 匹配要求唯一的目标侧")
    limb, blend_side = limbs[0], blend_sides[0]
    by_path = {joint.path: joint for joint in body.joints}
    paths = tuple(joint.body_joint for joint in blend_side.joints)
    if len(paths) != 3 or any(path not in by_path for path in paths):
        raise ValueError("Leg FK→IK 匹配要求完整的 Hip/Knee/Ankle Body 链")
    joints = tuple(by_path[path] for path in paths)
    line = tuple(
        end - start
        for start, end in zip(joints[0].world_position, joints[2].world_position)
    )
    fallback = min(
        joints[1].world_axes,
        key=lambda axis: abs(sum(a * b for a, b in zip(axis, line))),
    )
    pole = solve_limb_pole_position(
        joints[0].world_position,
        joints[1].world_position,
        joints[2].world_position,
        fallback,
        limb_label="Leg",
        distance_scale=pole_distance_scale,
    )
    blend_plug = f"{blend.settings_path}.{blend_side.attribute}"
    writable = tuple(
        f"{path}.{channel}"
        for path, channels in (
            (
                limb.ankle_control_path,
                (
                    "translateX", "translateY", "translateZ",
                    "rotateX", "rotateY", "rotateZ",
                ),
            ),
            (limb.pole_control_path, ("translateX", "translateY", "translateZ")),
        )
        for channel in channels
    ) + (blend_plug,)
    return BodyLegFkToIkPlan(
        side,
        blend_plug,
        limb.ankle_control_path,
        limb.pole_control_path,
        joints[2].world_position,
        joints[2].world_axes,
        pole,
        paths,
        tuple(joint.world_position for joint in joints),
        (limb.ankle_control_path, limb.pole_control_path, *paths),
        writable,
    )


def audit_body_leg_fk_to_ik_preflight(
    plan: BodyLegFkToIkPlan,
    state: BodyLegFkToIkSceneState,
    *,
    tolerance: float = 1e-6,
) -> tuple[BodyLegMatchIssue, ...]:
    issues = []
    missing = tuple(sorted(set(plan.required_paths) - set(state.existing_paths)))
    if missing:
        issues.append(BodyLegMatchIssue(
            "missing_paths", "Leg FK→IK 匹配节点缺失", "、".join(missing)
        ))
    locked = tuple(sorted(
        set(plan.required_writable_plugs) - set(state.writable_plugs)
    ))
    if locked:
        issues.append(BodyLegMatchIssue(
            "unwritable_channels", "Leg FK→IK 匹配通道不可写", "、".join(locked)
        ))
    if abs(state.blend_value) > tolerance:
        issues.append(BodyLegMatchIssue(
            "not_in_fk_mode", "目标腿当前不是 FK 模式", plan.side.value
        ))
    if (
        len(state.body_joint_positions) != len(plan.body_joint_positions)
        or any(
            not _close(actual, expected, tolerance)
            for actual, expected in zip(
                state.body_joint_positions, plan.body_joint_positions
            )
        )
        or len(state.ankle_axes) != 3
        or any(
            not _close(actual, expected, tolerance)
            for actual, expected in zip(state.ankle_axes, plan.ankle_axes)
        )
    ):
        issues.append(BodyLegMatchIssue(
            "pose_drift", "Leg FK→IK 匹配姿态已变化", plan.side.value
        ))
    return tuple(issues)


def audit_body_leg_fk_to_ik_result(
    plan: BodyLegFkToIkPlan,
    body: BodySkeletonSnapshot,
    blend_value: float,
    *,
    position_tolerance: float = 1e-3,
    axis_tolerance: float = 1e-3,
) -> tuple[BodyLegMatchIssue, ...]:
    issues = []
    if abs(blend_value - 1.0) > 1e-6:
        issues.append(BodyLegMatchIssue(
            "blend_not_ik", "Leg FK→IK 切换后 blend 未到 IK", plan.side.value
        ))
    by_path = {joint.path: joint for joint in body.joints}
    for path, expected in zip(plan.body_joint_paths, plan.body_joint_positions):
        current = by_path.get(path)
        if current is None or not _close(
            current.world_position, expected, position_tolerance
        ):
            issues.append(BodyLegMatchIssue(
                "position_pop", "Leg FK→IK 切换后关节位置跳变", path
            ))
    ankle = by_path.get(plan.body_joint_paths[2])
    if ankle is None or any(
        not _close(actual, expected, axis_tolerance)
        for actual, expected in zip(ankle.world_axes, plan.ankle_axes)
    ):
        issues.append(BodyLegMatchIssue(
            "ankle_orientation_pop",
            "Leg FK→IK 切换后 Ankle 朝向跳变",
            plan.body_joint_paths[2],
        ))
    return tuple(issues)


def plan_body_leg_ik_to_fk(
    body: BodySkeletonSnapshot,
    fk_controls: BodyLegFkControlPlan,
    blend: BodyLegBlendPlan,
    side: FitBuildSide,
) -> BodyLegIkToFkPlan:
    if side not in (FitBuildSide.RIGHT, FitBuildSide.LEFT):
        raise ValueError("Leg IK→FK 匹配只接受 Left 或 Right")
    controls = tuple(
        spec for spec in fk_controls.controls if spec.side is side
    )
    blend_sides = tuple(spec for spec in blend.sides if spec.side is side)
    if len(controls) != 3 or len(blend_sides) != 1:
        raise ValueError("Leg IK→FK 匹配要求唯一的三层 FK 控制链")
    by_path = {joint.path: joint for joint in body.joints}
    paths = tuple(joint.body_joint for joint in blend_sides[0].joints)
    if len(paths) != 3 or any(path not in by_path for path in paths):
        raise ValueError("Leg IK→FK 匹配要求完整的 Hip/Knee/Ankle Body 链")
    joints = tuple(by_path[path] for path in paths)
    control_paths = tuple(control.control_path for control in controls)
    driver_paths = tuple(control.driven_joint for control in controls)
    blend_plug = f"{blend.settings_path}.{blend_sides[0].attribute}"
    writable = tuple(
        f"{path}.rotate{axis}"
        for path in control_paths
        for axis in "XYZ"
    ) + (blend_plug,)
    return BodyLegIkToFkPlan(
        side,
        blend_plug,
        control_paths,
        tuple(joint.world_axes for joint in joints),
        paths,
        tuple(joint.world_position for joint in joints),
        tuple(joint.world_axes for joint in joints),
        (*control_paths, *driver_paths, *paths),
        writable,
    )


def audit_body_leg_ik_to_fk_preflight(
    plan: BodyLegIkToFkPlan,
    state: BodyLegIkToFkSceneState,
    *,
    tolerance: float = 1e-6,
) -> tuple[BodyLegMatchIssue, ...]:
    issues = []
    missing = tuple(sorted(set(plan.required_paths) - set(state.existing_paths)))
    if missing:
        issues.append(BodyLegMatchIssue(
            "missing_paths", "Leg IK→FK 匹配节点缺失", "、".join(missing)
        ))
    locked = tuple(sorted(
        set(plan.required_writable_plugs) - set(state.writable_plugs)
    ))
    if locked:
        issues.append(BodyLegMatchIssue(
            "unwritable_channels", "Leg IK→FK 匹配通道不可写", "、".join(locked)
        ))
    if abs(state.blend_value - 1.0) > tolerance:
        issues.append(BodyLegMatchIssue(
            "not_in_ik_mode", "目标腿当前不是 IK 模式", plan.side.value
        ))
    if (
        len(state.body_joint_positions) != len(plan.body_joint_positions)
        or any(
            not _close(actual, expected, tolerance)
            for actual, expected in zip(
                state.body_joint_positions, plan.body_joint_positions
            )
        )
        or len(state.body_joint_axes) != len(plan.body_joint_axes)
        or any(
            any(
                not _close(actual_axis, expected_axis, tolerance)
                for actual_axis, expected_axis in zip(actual, expected)
            )
            for actual, expected in zip(
                state.body_joint_axes, plan.body_joint_axes
            )
        )
    ):
        issues.append(BodyLegMatchIssue(
            "pose_drift", "Leg IK→FK 匹配姿态已变化", plan.side.value
        ))
    return tuple(issues)


def audit_body_leg_ik_to_fk_result(
    plan: BodyLegIkToFkPlan,
    body: BodySkeletonSnapshot,
    blend_value: float,
    *,
    position_tolerance: float = 1e-3,
    axis_tolerance: float = 1e-3,
) -> tuple[BodyLegMatchIssue, ...]:
    issues = []
    if abs(blend_value) > 1e-6:
        issues.append(BodyLegMatchIssue(
            "blend_not_fk", "Leg IK→FK 切换后 blend 未到 FK", plan.side.value
        ))
    by_path = {joint.path: joint for joint in body.joints}
    for path, expected_position, expected_axes in zip(
        plan.body_joint_paths,
        plan.body_joint_positions,
        plan.body_joint_axes,
    ):
        current = by_path.get(path)
        if current is None or not _close(
            current.world_position, expected_position, position_tolerance
        ):
            issues.append(BodyLegMatchIssue(
                "position_pop", "Leg IK→FK 切换后关节位置跳变", path
            ))
        if current is None or any(
            not _close(actual, expected, axis_tolerance)
            for actual, expected in zip(current.world_axes, expected_axes)
        ):
            issues.append(BodyLegMatchIssue(
                "orientation_pop", "Leg IK→FK 切换后关节朝向跳变", path
            ))
    return tuple(issues)


def _close(left, right, tolerance):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
