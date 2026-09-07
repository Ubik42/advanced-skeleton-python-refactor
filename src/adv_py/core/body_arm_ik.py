from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_arm_mechanisms import BodyArmMechanismPlan, BodyArmMechanismRole
from .body_limb_ik import BodyLimbIkValidationError, solve_limb_pole_position
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


BodyArmIkValidationError = BodyLimbIkValidationError


@dataclass(frozen=True, slots=True)
class BodyArmIkSpec:
    side: FitBuildSide
    chain: tuple[str, str, str]
    root_path: str
    wrist_offset_path: str
    wrist_offset_name: str
    wrist_control_path: str
    wrist_control_name: str
    pole_offset_path: str
    pole_offset_name: str
    pole_control_path: str
    pole_control_name: str
    handle_name: str
    pole_constraint_name: str
    wrist_position: Vector3
    wrist_axes: AxisFrame
    pole_position: Vector3
    radius: float
    wrist_constraint_name: str


@dataclass(frozen=True, slots=True)
class BodyArmIkPlan:
    root_path: str
    root_name: str
    limbs: tuple[BodyArmIkSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmIkState:
    side: FitBuildSide
    wrist_control_path: str
    wrist_parent_path: str | None
    pole_control_path: str
    pole_parent_path: str | None
    handle_name: str
    pole_constraint_name: str
    handle_parent_path: str | None
    joint_list: tuple[str, ...]
    pole_source: str | None
    wrist_position: Vector3
    pole_position: Vector3
    wrist_shape: str | None
    pole_shape: str | None
    wrist_translation: Vector3
    wrist_rotation: Vector3
    pole_translation: Vector3
    pole_rotation: Vector3
    wrist_constraint_name: str
    wrist_source: str | None
    wrist_driven_joint: str | None


@dataclass(frozen=True, slots=True)
class BodyArmIkSnapshot:
    root_path: str
    limbs: tuple[BodyArmIkState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmIkIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_arm_ik(
    body: BodySkeletonSnapshot,
    mechanisms: BodyArmMechanismPlan,
    *,
    radius: float = 1.5,
    pole_distance_scale: float = 0.75,
) -> BodyArmIkPlan:
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or value <= 0
        for value in (radius, pole_distance_scale)
    ):
        raise BodyArmIkValidationError("IK 控制尺寸参数必须是正有限数值")
    body_by_name = {joint.name: joint for joint in body.joints}
    root_name = "AdvPy_ArmIKControls"
    root_path = f"|{root_name}"
    limbs = []
    for side_name, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        sources = tuple(body_by_name[f"{name}_{side_name}"] for name in ("Shoulder", "Elbow", "Wrist"))
        drivers = tuple(
            spec.path
            for spec in mechanisms.joints
            if spec.side is side and spec.role is BodyArmMechanismRole.IK
        )
        if len(drivers) != 3:
            raise BodyArmIkValidationError("IK mechanism 必须为每侧提供三关节链")
        shoulder, elbow, wrist = (joint.world_position for joint in sources)
        pole = solve_arm_pole_position(
            shoulder,
            elbow,
            wrist,
            sources[1].world_axes[2],
            distance_scale=float(pole_distance_scale),
        )
        wrist_offset_name = f"AdvPy_ArmIKOffset_{side_name}"
        wrist_control_name = f"AdvPy_ArmIK_{side_name}"
        pole_offset_name = f"AdvPy_ArmPVOffset_{side_name}"
        pole_control_name = f"AdvPy_ArmPV_{side_name}"
        wrist_offset_path = f"{root_path}|{wrist_offset_name}"
        pole_offset_path = f"{root_path}|{pole_offset_name}"
        limbs.append(BodyArmIkSpec(
            side, drivers, root_path,
            wrist_offset_path, wrist_offset_name,
            f"{wrist_offset_path}|{wrist_control_name}", wrist_control_name,
            pole_offset_path, pole_offset_name,
            f"{pole_offset_path}|{pole_control_name}", pole_control_name,
            f"AdvPy_ArmIKHandle_{side_name}", f"AdvPy_ArmPVConstraint_{side_name}",
            wrist, sources[2].world_axes, pole, float(radius),
            f"AdvPy_ArmIKWristOrient_{side_name}",
        ))
    return BodyArmIkPlan(root_path, root_name, tuple(limbs))


def audit_body_arm_ik(plan: BodyArmIkPlan, snapshot: BodyArmIkSnapshot, *, tolerance: float = 1e-4, check_initial_pose: bool = True) -> tuple[BodyArmIkIssue, ...]:
    issues = []
    if snapshot.root_path != plan.root_path:
        issues.append(BodyArmIkIssue("ik_root_mismatch", "Arm IK 控制根不一致"))
    actual = {state.side: state for state in snapshot.limbs}
    for spec in plan.limbs:
        state = actual.get(spec.side)
        if state is None:
            issues.append(BodyArmIkIssue("missing_ik_limb", "缺少 Arm IK 侧", spec.side.value))
            continue
        checks = (
            (state.wrist_control_path == spec.wrist_control_path and state.wrist_parent_path == spec.wrist_offset_path, "ik_wrist_hierarchy", "Wrist IK 控制父链不一致"),
            (state.pole_control_path == spec.pole_control_path and state.pole_parent_path == spec.pole_offset_path, "ik_pole_hierarchy", "Pole Vector 控制父链不一致"),
            (state.handle_name == spec.handle_name and state.handle_parent_path == spec.wrist_control_path, "ik_handle_mismatch", "IK Handle 或父级不一致"),
            (state.pole_constraint_name == spec.pole_constraint_name, "ik_pole_constraint", "Pole Vector 约束名称不一致"),
            (state.wrist_constraint_name == spec.wrist_constraint_name and state.wrist_source == spec.wrist_control_path and state.wrist_driven_joint == spec.chain[2], "ik_wrist_orientation", "Wrist IK 朝向驱动不一致"),
            (state.joint_list == spec.chain[:2], "ik_chain_mismatch", "RP IK 求解链不一致"),
            (state.pole_source == spec.pole_control_path, "ik_pole_wiring", "Pole Vector 连线不一致"),
            (state.wrist_shape == "nurbsCurve" and state.pole_shape == "nurbsCurve", "ik_shape_mismatch", "IK 控制缺少 NURBS 曲线"),
        )
        if check_initial_pose:
            checks += (
                (_close(state.wrist_position, spec.wrist_position, tolerance) and _close(state.pole_position, spec.pole_position, tolerance), "ik_position_mismatch", "IK 控制初始位置不一致"),
                (all(_close(value, (0.0, 0.0, 0.0), tolerance) for value in (state.wrist_translation, state.wrist_rotation, state.pole_translation, state.pole_rotation)), "ik_channels_nonzero", "IK 控制本地通道未归零"),
            )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyArmIkIssue(code, message, spec.side.value))
    return tuple(issues)


def solve_arm_pole_position(
    shoulder: Vector3,
    elbow: Vector3,
    wrist: Vector3,
    fallback_axis: Vector3,
    *,
    distance_scale: float = 0.75,
) -> Vector3:
    return solve_limb_pole_position(
        shoulder,
        elbow,
        wrist,
        fallback_axis,
        limb_label="Arm",
        distance_scale=distance_scale,
    )


def _close(a, b, tolerance): return all(abs(x - y) <= tolerance for x, y in zip(a, b))
