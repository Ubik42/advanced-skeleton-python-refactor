from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

from .body_leg_blend import BodyLegBlendPlan
from .body_leg_ik import BodyLegIkPlan
from .body_leg_controls import BodyLegFkControlPlan
from .body_leg_foot import BodyLegFootPlan, BodyLegFootSnapshot
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
    toe_body_path: str
    ankle_ik_driver_path: str
    toe_ik_driver_path: str
    toe_body_position: Vector3
    toe_body_axes: AxisFrame
    toe_control_path: str
    foot_attribute_plugs: tuple[str, ...]
    required_paths: tuple[str, ...]
    required_writable_plugs: tuple[str, ...]
    foot_reset_values: tuple[tuple[str, float], ...] = ()
    roll_rotation_plugs: tuple[str, ...] = ()
    toe_end_body_path: str | None = None
    toe_end_ik_driver_path: str | None = None
    toe_end_body_position: Vector3 | None = None
    toe_end_body_axes: AxisFrame | None = None


@dataclass(frozen=True, slots=True)
class BodyLegFkToIkSceneState:
    existing_paths: tuple[str, ...]
    writable_plugs: tuple[str, ...]
    blend_value: float
    body_joint_positions: tuple[Vector3, ...]
    ankle_axes: tuple[Vector3, ...]
    toe_body_axes: tuple[Vector3, ...]
    foot_attribute_values: tuple[tuple[str, float], ...]
    roll_rotation_values: tuple[tuple[str, float], ...] = ()
    toe_end_body_axes: tuple[Vector3, ...] = ()


@dataclass(frozen=True, slots=True)
class BodyLegIkToFkPlan:
    side: FitBuildSide
    blend_plug: str
    fk_control_paths: tuple[str, ...]
    fk_control_axes: tuple[AxisFrame, ...]
    fk_segment_plugs: tuple[str, str]
    fk_segment_translations: tuple[float, float]
    body_joint_paths: tuple[str, ...]
    body_joint_positions: tuple[Vector3, ...]
    body_joint_axes: tuple[AxisFrame, ...]
    required_paths: tuple[str, ...]
    required_writable_plugs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodyLegIkToFkSceneState:
    existing_paths: tuple[str, ...]
    writable_plugs: tuple[str, ...]
    blend_value: float
    body_joint_positions: tuple[Vector3, ...]
    body_joint_axes: tuple[AxisFrame, ...]
    fk_segment_translations: tuple[float, float]


@dataclass(frozen=True, slots=True)
class BodyLegMatchIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_leg_fk_to_ik(
    body: BodySkeletonSnapshot,
    ik: BodyLegIkPlan,
    blend: BodyLegBlendPlan,
    foot: BodyLegFootPlan,
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
    foot_sides = tuple(spec for spec in foot.sides if spec.side is side)
    if len(foot_sides) != 1:
        raise ValueError("Leg FK→IK 匹配要求唯一的目标侧 Foot")
    foot_side = foot_sides[0]
    by_path = {joint.path: joint for joint in body.joints}
    by_name = {joint.name: joint for joint in body.joints}
    wanted_names = tuple(
        f"{name}_{side.value}" for name in ("Hip", "Knee", "Ankle")
    )
    paths = tuple(
        by_name[name].path for name in wanted_names if name in by_name
    )
    blended_paths = {joint.body_joint for joint in blend_side.joints}
    if (
        len(paths) != 3
        or any(path not in by_path for path in paths)
        or any(path not in blended_paths for path in paths)
    ):
        raise ValueError("Leg FK→IK 匹配要求完整的 Hip/Knee/Ankle Body 链")
    joints = tuple(by_path[path] for path in paths)
    toe_name = f"Toes_{side.value}"
    toe = by_name.get(toe_name)
    toe_blend = next(
        (
            joint for joint in blend_side.joints
            if toe is not None and joint.body_joint == toe.path
        ),
        None,
    )
    if toe is None or toe_blend is None:
        raise ValueError("Leg FK→IK 匹配要求 Toes Body 与 IK driver 输出")
    toe_end = by_name.get(f"ToesEnd_{side.value}")
    toe_end_blend = next(
        (joint for joint in blend_side.joints
         if toe_end is not None and joint.body_joint == toe_end.path), None)
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
    foot_plugs = tuple(
        f"{foot_side.ankle_control_path}.{attribute}"
        for attribute in foot_side.attributes
        if attribute != "footPivotsVis"
    )
    foot_reset_values = tuple(
        (f"{foot_side.ankle_control_path}.{attribute}",
         foot_side.attribute_default(attribute))
        for attribute in foot_side.attributes
        if attribute != "footPivotsVis"
    )
    roll_rotation_plugs = tuple(
        f"{pivot.roll_control_path}.rotate{axis}"
        for pivot in foot_side.pivots if pivot.roll_control_path
        for axis in "XYZ"
    ) + tuple(
        f"{manual.control_path}.{channel}{axis}"
        for manual in foot_side.manual_pivots
        for channel in ("translate", "rotate")
        for axis in "XYZ"
    )
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
    ) + tuple(
        f"{foot_side.toe_control_path}.rotate{axis}" for axis in "XYZ"
    ) + foot_plugs + roll_rotation_plugs + (blend_plug,) + (
        tuple(f"{toe_end_blend.ik_driver}.rotate{axis}" for axis in "XYZ")
        if toe_end_blend is not None else ())
    return BodyLegFkToIkPlan(
        side=side,
        blend_plug=blend_plug,
        ankle_control_path=limb.ankle_control_path,
        pole_control_path=limb.pole_control_path,
        ankle_position=joints[2].world_position,
        ankle_axes=joints[2].world_axes,
        pole_position=pole,
        body_joint_paths=paths,
        body_joint_positions=tuple(joint.world_position for joint in joints),
        toe_body_path=toe.path,
        ankle_ik_driver_path=limb.chain[2],
        toe_ik_driver_path=toe_blend.ik_driver,
        toe_body_position=toe.world_position,
        toe_body_axes=toe.world_axes,
        toe_control_path=foot_side.toe_control_path,
        foot_attribute_plugs=foot_plugs,
        foot_reset_values=foot_reset_values,
        roll_rotation_plugs=roll_rotation_plugs,
        required_paths=(
            limb.ankle_control_path,
            limb.pole_control_path,
            foot_side.toe_control_path,
            *(pivot.roll_control_path for pivot in foot_side.pivots
              if pivot.roll_control_path),
            *(manual.control_path for manual in foot_side.manual_pivots),
            *paths,
            toe.path,
            limb.chain[2],
            toe_blend.ik_driver,
            *((toe_end.path, toe_end_blend.ik_driver)
              if toe_end_blend is not None else ()),
        ),
        required_writable_plugs=writable,
        toe_end_body_path=(toe_end.path if toe_end_blend is not None else None),
        toe_end_ik_driver_path=(toe_end_blend.ik_driver
                                if toe_end_blend is not None else None),
        toe_end_body_position=(toe_end.world_position
                               if toe_end_blend is not None else None),
        toe_end_body_axes=(toe_end.world_axes
                           if toe_end_blend is not None else None),
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
        tuple(plug for plug, _ in state.foot_attribute_values)
        != plan.foot_attribute_plugs
    ):
        issues.append(BodyLegMatchIssue(
            "foot_state_incomplete",
            "Leg FK→IK 匹配缺少完整 Foot 属性状态",
            plan.side.value,
        ))
    if tuple(plug for plug, _ in state.roll_rotation_values) != (
            plan.roll_rotation_plugs):
        issues.append(BodyLegMatchIssue(
            "roll_state_incomplete",
            "Leg FK→IK 匹配缺少 Roll 控制旋转状态",
            plan.side.value))
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
    if (
        len(state.toe_body_axes) != 3
        or any(
            not _close(actual, expected, tolerance)
            for actual, expected in zip(
                state.toe_body_axes, plan.toe_body_axes
            )
        )
    ):
        issues.append(BodyLegMatchIssue(
            "pose_drift",
            "Leg FK→IK 匹配 Toes 姿态已变化",
            plan.side.value,
        ))
    if (plan.toe_end_body_axes is not None and (
            len(state.toe_end_body_axes) != 3
            or any(not _close(actual, expected, tolerance)
                   for actual, expected in zip(
                       state.toe_end_body_axes,
                       plan.toe_end_body_axes)))):
        issues.append(BodyLegMatchIssue(
            "pose_drift", "Leg FK→IK 匹配 ToesEnd 姿态已变化",
            plan.side.value))
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
    toe = by_path.get(plan.toe_body_path)
    if toe is None or not _close(
        toe.world_position, plan.toe_body_position, position_tolerance
    ):
        issues.append(BodyLegMatchIssue(
            "toe_position_pop",
            "Leg FK→IK 切换后 Toes 位置跳变",
            plan.toe_body_path,
        ))
    if toe is None or any(
        not _close(actual, expected, axis_tolerance)
        for actual, expected in zip(toe.world_axes, plan.toe_body_axes)
    ):
        issues.append(BodyLegMatchIssue(
            "toe_orientation_pop",
            "Leg FK→IK 切换后 Toes 朝向跳变",
            plan.toe_body_path,
        ))
    if plan.toe_end_body_path is not None:
        toe_end = by_path.get(plan.toe_end_body_path)
        if (toe_end is None or plan.toe_end_body_position is None
                or not _close(toe_end.world_position,
                              plan.toe_end_body_position,
                              position_tolerance)):
            issues.append(BodyLegMatchIssue(
                "toe_end_position_pop", "Leg FK→IK 切换后 ToesEnd 位置跳变",
                plan.toe_end_body_path))
        if (toe_end is None or plan.toe_end_body_axes is None
                or any(not _close(actual, expected, axis_tolerance)
                       for actual, expected in zip(
                           toe_end.world_axes, plan.toe_end_body_axes))):
            issues.append(BodyLegMatchIssue(
                "toe_end_orientation_pop", "Leg FK→IK 切换后 ToesEnd 朝向跳变",
                plan.toe_end_body_path))
    return tuple(issues)


def audit_body_leg_fk_to_ik_foot_result(
    plan: BodyLegFkToIkPlan,
    snapshot: BodyLegFootSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyLegMatchIssue, ...]:
    state = next(
        (value for value in snapshot.sides if value.side is plan.side), None
    )
    if state is None:
        return (BodyLegMatchIssue(
            "foot_match_state_missing",
            "Leg FK→IK 匹配后缺少目标侧 Foot 状态",
            plan.side.value,
        ),)
    expected = plan.foot_reset_values or tuple(
        (plug, 0.0) for plug in plan.foot_attribute_plugs)
    actual_values = dict(state.attribute_values)
    if (any(plug not in actual_values
            or abs(actual_values[plug] - wanted) > tolerance
            for plug, wanted in expected)):
        return (BodyLegMatchIssue(
            "foot_match_values",
            "Leg FK→IK 匹配后的 Foot 属性不一致",
            plan.side.value,
        ),)
    roll_rotations = tuple(
        component
        for pivot in state.pivots if pivot.roll_control_path
        for component in (pivot.roll_control_rotation or ())
    ) + tuple(
        component
        for manual in state.manual_pivots
        for component in (*(manual.local_translation or ()),
                          *(manual.local_rotation or ()))
    )
    if (len(roll_rotations) != len(plan.roll_rotation_plugs)
            or any(abs(value) > tolerance for value in roll_rotations)):
        return (BodyLegMatchIssue(
            "foot_roll_controls", "Leg FK→IK 匹配后 Roll 控制未归零",
            plan.side.value),)
    return ()


def plan_body_leg_ik_to_fk(
    body: BodySkeletonSnapshot,
    fk_controls: BodyLegFkControlPlan,
    blend: BodyLegBlendPlan,
    side: FitBuildSide,
) -> BodyLegIkToFkPlan:
    if side not in (FitBuildSide.RIGHT, FitBuildSide.LEFT):
        raise ValueError("Leg IK→FK 匹配只接受 Left 或 Right")
    control_by_name = {
        spec.control_name: spec
        for spec in fk_controls.controls
        if spec.side is side
    }
    terminal_control = f"AdvPy_ToesEndFK_{side.value}" in control_by_name
    control_names = (
        f"AdvPy_HipFK_{side.value}",
        f"AdvPy_KneeFK_{side.value}",
        f"AdvPy_AnkleFK_{side.value}",
        f"AdvPy_ToesFK_{side.value}",
    ) + ((f"AdvPy_ToesEndFK_{side.value}",)
         if terminal_control else ())
    controls = tuple(
        control_by_name[name]
        for name in control_names
        if name in control_by_name
    )
    blend_sides = tuple(spec for spec in blend.sides if spec.side is side)
    if len(controls) != len(control_names) or len(blend_sides) != 1:
        raise ValueError("Leg IK→FK 匹配缺少目标侧 FK 控制链")
    by_path = {joint.path: joint for joint in body.joints}
    by_name = {joint.name: joint for joint in body.joints}
    joint_names = (("Hip", "Knee", "Ankle", "Toes", "ToesEnd")
                   if terminal_control else
                   ("Hip", "Knee", "Ankle", "Toes"))
    wanted_names = tuple(f"{name}_{side.value}" for name in joint_names)
    paths = tuple(
        by_name[name].path for name in wanted_names if name in by_name
    )
    blended_paths = {joint.body_joint for joint in blend_sides[0].joints}
    if (
        len(paths) != len(joint_names)
        or any(path not in by_path for path in paths)
        or any(path not in blended_paths for path in paths)
    ):
        raise ValueError("Leg IK→FK 匹配要求完整的目标侧 Body 链")
    joints = tuple(by_path[path] for path in paths)
    control_paths = tuple(control.control_path for control in controls)
    driver_paths = tuple(control.driven_joint for control in controls)
    segment_axes_and_values = tuple(
        _signed_local_axis_distance(parent, child)
        for parent, child in zip(joints, joints[1:3])
    )
    segment_plugs = tuple(
        f"{path}.translate{axis}"
        for path, (axis, _) in zip(driver_paths[1:3], segment_axes_and_values)
    )
    segment_translations = tuple(
        value for _, value in segment_axes_and_values
    )
    blend_plug = f"{blend.settings_path}.{blend_sides[0].attribute}"
    writable = tuple(
        f"{path}.rotate{axis}"
        for path in control_paths
        for axis in "XYZ"
    ) + segment_plugs + (blend_plug,)
    return BodyLegIkToFkPlan(
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
    fk_segment_translations: tuple[float, float],
    *,
    position_tolerance: float = 1e-3,
    axis_tolerance: float = 1e-3,
) -> tuple[BodyLegMatchIssue, ...]:
    issues = []
    if abs(blend_value) > 1e-6:
        issues.append(BodyLegMatchIssue(
            "blend_not_fk", "Leg IK→FK 切换后 blend 未到 FK", plan.side.value
        ))
    if (
        len(fk_segment_translations) != len(plan.fk_segment_translations)
        or not _close(
            fk_segment_translations,
            plan.fk_segment_translations,
            position_tolerance,
        )
    ):
        issues.append(BodyLegMatchIssue(
            "segment_length_mismatch",
            "Leg IK→FK 切换后 FK 段长不一致",
            plan.side.value,
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


def _signed_local_axis_distance(
    parent, child, *, tolerance: float = 1e-3
) -> tuple[str, float]:
    delta = tuple(
        child_value - parent_value
        for parent_value, child_value in zip(
            parent.world_position, child.world_position
        )
    )
    length = sqrt(sum(value * value for value in delta))
    projections = tuple(
        sum(value * component for value, component in zip(delta, axis))
        for axis in parent.world_axes
    )
    axis_index = max(range(3), key=lambda index: abs(projections[index]))
    projected = projections[axis_index]
    if (
        not isfinite(length)
        or not isfinite(projected)
        or length <= 1e-6
        or abs(abs(projected) - length) > tolerance
    ):
        raise ValueError(
            "Leg IK→FK 匹配要求 Body 段沿父关节一个明确的本地主轴"
        )
    scale=parent.world_scale[axis_index]
    if not isfinite(scale) or scale<=1e-8:
        raise ValueError("Leg IK→FK 父级缩放无效")
    return "XYZ"[axis_index], projected/scale
