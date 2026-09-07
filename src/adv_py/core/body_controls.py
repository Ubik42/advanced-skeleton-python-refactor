from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import AxisFrame, FitBuildSide


Vector3 = tuple[float, float, float]


class BodyControlValidationError(ValueError):
    """Raised when Body controls cannot be planned safely."""


@dataclass(frozen=True, slots=True)
class BodyArmFkControlSpec:
    side: FitBuildSide
    driven_joint: str
    offset_path: str
    offset_name: str
    control_path: str
    control_name: str
    parent_path: str
    constraint_name: str
    world_position: Vector3
    world_axes: AxisFrame
    radius: float


@dataclass(frozen=True, slots=True)
class BodyArmFkControlPlan:
    root_path: str
    root_name: str
    controls: tuple[BodyArmFkControlSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmFkControlState:
    offset_path: str
    offset_parent_path: str | None
    control_path: str
    control_parent_path: str | None
    constraint_name: str
    source_control: str | None
    driven_joint: str | None
    world_position: Vector3
    world_axes: AxisFrame
    local_translation: Vector3
    local_rotation: Vector3
    shape_type: str | None


@dataclass(frozen=True, slots=True)
class BodyArmFkControlSnapshot:
    root_path: str
    controls: tuple[BodyArmFkControlState, ...]


@dataclass(frozen=True, slots=True)
class BodyControlIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_arm_fk_controls(
    body: BodySkeletonSnapshot,
    *,
    radius: float = 1.5,
) -> BodyArmFkControlPlan:
    if (
        isinstance(radius, bool)
        or not isinstance(radius, (int, float))
        or not isfinite(float(radius))
        or radius <= 0
    ):
        raise BodyControlValidationError("Arm FK 控制半径必须是正有限数值")

    by_name = {state.name: state for state in body.joints}
    required_names = tuple(
        f"{joint}_{side}"
        for side in ("R", "L")
        for joint in ("Shoulder", "Elbow", "Wrist")
    )
    if len(by_name) != len(body.joints) or any(
        name not in by_name for name in required_names
    ):
        raise BodyControlValidationError("Body 缺少唯一的双臂 Shoulder/Elbow/Wrist")

    root_name = "AdvPy_ArmFKControls"
    root_path = f"|{root_name}"
    controls: list[BodyArmFkControlSpec] = []
    for side, side_value in (
        ("R", FitBuildSide.RIGHT),
        ("L", FitBuildSide.LEFT),
    ):
        parent_path = root_path
        previous_joint = None
        for joint_name in ("Shoulder", "Elbow", "Wrist"):
            state = by_name[f"{joint_name}_{side}"]
            if state.side is not side_value:
                raise BodyControlValidationError(
                    f"{state.name} 的 Body side 与名称不一致"
                )
            if previous_joint is not None and state.parent_path != previous_joint:
                raise BodyControlValidationError(
                    f"{state.name} 不在预期 Arm FK 父链上"
                )
            offset_name = f"AdvPy_{joint_name}FKOffset_{side}"
            control_name = f"AdvPy_{joint_name}FK_{side}"
            offset_path = f"{parent_path}|{offset_name}"
            control_path = f"{offset_path}|{control_name}"
            controls.append(
                BodyArmFkControlSpec(
                    side=side_value,
                    driven_joint=state.path,
                    offset_path=offset_path,
                    offset_name=offset_name,
                    control_path=control_path,
                    control_name=control_name,
                    parent_path=parent_path,
                    constraint_name=f"AdvPy_{joint_name}FKOrient_{side}",
                    world_position=state.world_position,
                    world_axes=state.world_axes,
                    radius=float(radius),
                )
            )
            parent_path = control_path
            previous_joint = state.path
    return BodyArmFkControlPlan(root_path, root_name, tuple(controls))


def audit_body_arm_fk_controls(
    plan: BodyArmFkControlPlan,
    snapshot: BodyArmFkControlSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyControlIssue, ...]:
    issues: list[BodyControlIssue] = []
    if snapshot.root_path != plan.root_path:
        issues.append(
            BodyControlIssue("control_root_mismatch", "Arm FK 控制根路径不一致")
        )
    expected = {spec.control_path: spec for spec in plan.controls}
    actual = {state.control_path: state for state in snapshot.controls}
    for path in sorted(set(expected) - set(actual)):
        issues.append(BodyControlIssue("missing_control", "缺少 Arm FK 控制", path))
    for path in sorted(set(actual) - set(expected)):
        issues.append(
            BodyControlIssue("unexpected_control", "存在计划外 Arm FK 控制", path)
        )
    for path in sorted(set(expected) & set(actual)):
        spec = expected[path]
        state = actual[path]
        if (
            state.offset_path != spec.offset_path
            or state.offset_parent_path != spec.parent_path
            or state.control_parent_path != spec.offset_path
        ):
            issues.append(
                BodyControlIssue("control_hierarchy_mismatch", "FK 控制父链不一致", path)
            )
        if state.constraint_name != spec.constraint_name:
            issues.append(
                BodyControlIssue("constraint_name_mismatch", "FK 约束名称不一致", path)
            )
        if (
            state.source_control != spec.control_path
            or state.driven_joint != spec.driven_joint
        ):
            issues.append(
                BodyControlIssue("constraint_wiring_mismatch", "FK 约束连接不一致", path)
            )
        if state.shape_type != "nurbsCurve":
            issues.append(
                BodyControlIssue("control_shape_mismatch", "FK 控制缺少 NURBS 曲线", path)
            )
        if not _vector_matches(state.world_position, spec.world_position, tolerance):
            issues.append(
                BodyControlIssue("control_position_mismatch", "FK 控制世界位置不一致", path)
            )
        if any(
            not _vector_matches(current, wanted, tolerance)
            for current, wanted in zip(state.world_axes, spec.world_axes)
        ):
            issues.append(
                BodyControlIssue("control_axes_mismatch", "FK 控制世界轴不一致", path)
            )
        if not _vector_matches(state.local_translation, (0.0, 0.0, 0.0), tolerance):
            issues.append(
                BodyControlIssue("nonzero_control_translation", "FK 控制 translate 未归零", path)
            )
        if not _vector_matches(state.local_rotation, (0.0, 0.0, 0.0), tolerance):
            issues.append(
                BodyControlIssue("nonzero_control_rotation", "FK 控制 rotate 未归零", path)
            )
    return tuple(issues)


def _vector_matches(left: Vector3, right: Vector3, tolerance: float) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))
