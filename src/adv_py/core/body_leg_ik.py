from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_leg_mechanisms import BodyLegMechanismPlan, BodyLegMechanismRole
from .body_limb_ik import BodyLimbIkValidationError, solve_limb_pole_position
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]
BodyLegIkValidationError = BodyLimbIkValidationError


@dataclass(frozen=True, slots=True)
class BodyLegIkSpec:
    side: FitBuildSide
    chain: tuple[str, str, str]
    root_path: str
    ankle_offset_path: str
    ankle_offset_name: str
    ankle_control_path: str
    ankle_control_name: str
    pole_offset_path: str
    pole_offset_name: str
    pole_control_path: str
    pole_control_name: str
    handle_name: str
    pole_constraint_name: str
    ankle_position: Vector3
    ankle_axes: AxisFrame
    pole_position: Vector3
    radius: float
    ankle_constraint_name: str


@dataclass(frozen=True, slots=True)
class BodyLegIkPlan:
    root_path: str
    root_name: str
    limbs: tuple[BodyLegIkSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLegIkState:
    side: FitBuildSide
    ankle_control_path: str
    ankle_parent_path: str | None
    pole_control_path: str
    pole_parent_path: str | None
    handle_name: str
    pole_constraint_name: str
    handle_parent_path: str | None
    joint_list: tuple[str, ...]
    pole_source: str | None
    ankle_position: Vector3
    pole_position: Vector3
    ankle_shape: str | None
    pole_shape: str | None
    ankle_translation: Vector3
    ankle_rotation: Vector3
    pole_translation: Vector3
    pole_rotation: Vector3
    ankle_constraint_name: str
    ankle_source: str | None
    ankle_driven_joint: str | None


@dataclass(frozen=True, slots=True)
class BodyLegIkSnapshot:
    root_path: str
    limbs: tuple[BodyLegIkState, ...]


@dataclass(frozen=True, slots=True)
class BodyLegIkIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_leg_ik(
    body: BodySkeletonSnapshot,
    mechanisms: BodyLegMechanismPlan,
    *,
    radius: float = 1.75,
    pole_distance_scale: float = 0.75,
) -> BodyLegIkPlan:
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or value <= 0
        for value in (radius, pole_distance_scale)
    ):
        raise BodyLegIkValidationError("Leg IK 控制尺寸参数必须是正有限数值")

    body_by_name = {joint.name: joint for joint in body.joints}
    required = tuple(
        f"{name}_{suffix}"
        for suffix in ("R", "L")
        for name in ("Hip", "Knee", "Ankle")
    )
    if len(body_by_name) != len(body.joints) or any(
        name not in body_by_name for name in required
    ):
        raise BodyLegIkValidationError("Body 缺少唯一的双腿 Hip/Knee/Ankle")
    ik_by_source = {
        spec.source_joint: spec.path
        for spec in mechanisms.joints
        if spec.role is BodyLegMechanismRole.IK
    }

    root_name = "AdvPy_LegIKControls"
    root_path = f"|{root_name}"
    limbs = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        sources = tuple(
            body_by_name[f"{name}_{suffix}"]
            for name in ("Hip", "Knee", "Ankle")
        )
        if any(source.side is not side for source in sources):
            raise BodyLegIkValidationError("Leg Body side 与名称不一致")
        try:
            drivers = tuple(ik_by_source[source.path] for source in sources)
        except KeyError as exc:
            raise BodyLegIkValidationError(
                "Leg IK mechanism 必须为每侧提供完整三关节链"
            ) from exc
        hip, knee, ankle = (joint.world_position for joint in sources)
        fallback_axis = _least_parallel_axis(
            hip,
            ankle,
            sources[1].world_axes,
        )
        pole = solve_limb_pole_position(
            hip,
            knee,
            ankle,
            fallback_axis,
            limb_label="Leg",
            distance_scale=float(pole_distance_scale),
        )
        ankle_offset_name = f"AdvPy_LegIKOffset_{suffix}"
        ankle_control_name = f"AdvPy_LegIK_{suffix}"
        pole_offset_name = f"AdvPy_LegPVOffset_{suffix}"
        pole_control_name = f"AdvPy_LegPV_{suffix}"
        ankle_offset_path = f"{root_path}|{ankle_offset_name}"
        pole_offset_path = f"{root_path}|{pole_offset_name}"
        limbs.append(BodyLegIkSpec(
            side=side,
            chain=drivers,
            root_path=root_path,
            ankle_offset_path=ankle_offset_path,
            ankle_offset_name=ankle_offset_name,
            ankle_control_path=f"{ankle_offset_path}|{ankle_control_name}",
            ankle_control_name=ankle_control_name,
            pole_offset_path=pole_offset_path,
            pole_offset_name=pole_offset_name,
            pole_control_path=f"{pole_offset_path}|{pole_control_name}",
            pole_control_name=pole_control_name,
            handle_name=f"AdvPy_LegIKHandle_{suffix}",
            pole_constraint_name=f"AdvPy_LegPVConstraint_{suffix}",
            ankle_position=ankle,
            ankle_axes=sources[2].world_axes,
            pole_position=pole,
            radius=float(radius),
            ankle_constraint_name=f"AdvPy_LegIKAnkleOrient_{suffix}",
        ))
    return BodyLegIkPlan(root_path, root_name, tuple(limbs))


def audit_body_leg_ik(
    plan: BodyLegIkPlan,
    snapshot: BodyLegIkSnapshot,
    *,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
) -> tuple[BodyLegIkIssue, ...]:
    issues = []
    if snapshot.root_path != plan.root_path:
        issues.append(BodyLegIkIssue("ik_root_mismatch", "Leg IK 控制根不一致"))
    actual = {state.side: state for state in snapshot.limbs}
    for spec in plan.limbs:
        state = actual.get(spec.side)
        if state is None:
            issues.append(BodyLegIkIssue(
                "missing_ik_limb", "缺少 Leg IK 侧", spec.side.value
            ))
            continue
        checks = (
            (
                state.ankle_control_path == spec.ankle_control_path
                and state.ankle_parent_path == spec.ankle_offset_path,
                "ik_ankle_hierarchy",
                "Ankle IK 控制父链不一致",
            ),
            (
                state.pole_control_path == spec.pole_control_path
                and state.pole_parent_path == spec.pole_offset_path,
                "ik_pole_hierarchy",
                "Pole Vector 控制父链不一致",
            ),
            (
                state.handle_name == spec.handle_name
                and state.handle_parent_path == spec.ankle_control_path,
                "ik_handle_mismatch",
                "IK Handle 或父级不一致",
            ),
            (
                state.pole_constraint_name == spec.pole_constraint_name,
                "ik_pole_constraint",
                "Pole Vector 约束名称不一致",
            ),
            (
                state.ankle_constraint_name == spec.ankle_constraint_name
                and state.ankle_source == spec.ankle_control_path
                and state.ankle_driven_joint == spec.chain[2],
                "ik_ankle_orientation",
                "Ankle IK 朝向驱动不一致",
            ),
            (
                state.joint_list == spec.chain[:2],
                "ik_chain_mismatch",
                "RP IK 求解链不一致",
            ),
            (
                state.pole_source == spec.pole_control_path,
                "ik_pole_wiring",
                "Pole Vector 连线不一致",
            ),
            (
                state.ankle_shape == "nurbsCurve"
                and state.pole_shape == "nurbsCurve",
                "ik_shape_mismatch",
                "IK 控制缺少 NURBS 曲线",
            ),
        )
        if check_initial_pose:
            checks += (
                (
                    _close(state.ankle_position, spec.ankle_position, tolerance)
                    and _close(state.pole_position, spec.pole_position, tolerance),
                    "ik_position_mismatch",
                    "IK 控制初始位置不一致",
                ),
                (
                    all(
                        _close(value, (0.0, 0.0, 0.0), tolerance)
                        for value in (
                            state.ankle_translation,
                            state.ankle_rotation,
                            state.pole_translation,
                            state.pole_rotation,
                        )
                    ),
                    "ik_channels_nonzero",
                    "IK 控制本地通道未归零",
                ),
            )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyLegIkIssue(code, message, spec.side.value))
    return tuple(issues)


def _close(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _least_parallel_axis(
    start: Vector3,
    end: Vector3,
    axes: AxisFrame,
) -> Vector3:
    line = tuple(b - a for a, b in zip(start, end))
    return min(
        axes,
        key=lambda axis: abs(sum(a * b for a, b in zip(axis, line))),
    )
