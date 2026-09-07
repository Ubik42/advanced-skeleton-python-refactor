from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import atan2, isfinite, sqrt

from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import FitBuildSide


Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]


class BodyArmTwistSegment(str, Enum):
    UPPER = "upper"
    LOWER = "lower"


class BodyArmTwistValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyArmTwistSegmentSpec:
    side: FitBuildSide
    segment: BodyArmTwistSegment
    path: str
    name: str
    parent_path: str
    start_joint: str
    end_joint: str
    constraint_name: str
    compose_name: str
    decompose_name: str
    quaternion_name: str


@dataclass(frozen=True, slots=True)
class BodyArmTwistJointSpec:
    side: FitBuildSide
    segment: BodyArmTwistSegment
    fraction: float
    path: str
    name: str
    parent_path: str
    start_joint: str
    end_joint: str
    constraint_name: str
    multiplier_name: str
    quaternion_name: str
    world_position: Vector3


@dataclass(frozen=True, slots=True)
class BodyArmTwistPlan:
    root_path: str
    root_name: str
    segments: tuple[BodyArmTwistSegmentSpec, ...]
    joints: tuple[BodyArmTwistJointSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmTwistSegmentState:
    side: FitBuildSide
    segment: BodyArmTwistSegment
    path: str
    parent_path: str | None
    constraint_name: str
    targets: tuple[str, ...]
    driven_path: str | None
    compose_name: str
    rotate_source: str | None
    rotate_order_source: str | None
    decompose_name: str
    decompose_source: str | None
    quaternion_name: str
    quaternion_x_source: str | None
    quaternion_w_source: str | None


@dataclass(frozen=True, slots=True)
class BodyArmTwistJointState:
    side: FitBuildSide
    segment: BodyArmTwistSegment
    path: str
    parent_path: str | None
    world_position: Vector3
    constraint_name: str
    targets: tuple[str, ...]
    weights: tuple[float, ...]
    driven_joint: str | None
    multiplier_name: str
    twist_source: str | None
    multiplier_scale: float
    rotate_x_source: str | None
    rotate_yz: tuple[float, float]


@dataclass(frozen=True, slots=True)
class BodyArmTwistSnapshot:
    root_path: str
    segments: tuple[BodyArmTwistSegmentState, ...]
    joints: tuple[BodyArmTwistJointState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmTwistIssue:
    code: str
    message: str
    subject: str | None = None


def project_twist_quaternion_x(
    quaternion: Quaternion,
    *,
    tolerance: float = 1e-8,
) -> Quaternion:
    """Project a rotation quaternion onto local X and choose the shortest sign."""

    if (
        len(quaternion) != 4
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(value)
            for value in quaternion
        )
        or isinstance(tolerance, bool)
        or not isfinite(tolerance)
        or tolerance <= 0.0
    ):
        raise BodyArmTwistValidationError("Arm twist 四元数或容差无效")
    x, _, _, w = (float(value) for value in quaternion)
    magnitude = sqrt(x * x + w * w)
    if magnitude <= tolerance:
        return (0.0, 0.0, 0.0, 1.0)
    x, w = x / magnitude, w / magnitude
    if w < 0.0:
        x, w = -x, -w
    return (x, 0.0, 0.0, w)


def twist_angle_x(quaternion: Quaternion) -> float:
    projected = project_twist_quaternion_x(quaternion)
    return 2.0 * atan2(projected[0], projected[3])


def plan_body_arm_twist(
    body: BodySkeletonSnapshot,
    *,
    joints_per_segment: int = 2,
) -> BodyArmTwistPlan:
    if (
        isinstance(joints_per_segment, bool)
        or not isinstance(joints_per_segment, int)
        or not 1 <= joints_per_segment <= 8
    ):
        raise BodyArmTwistValidationError("Arm twist 每段关节数量必须位于 1 到 8")
    by_name = {joint.name: joint for joint in body.joints}
    root_name = "AdvPy_ArmTwistJoints"
    root_path = f"|{root_name}"
    segments = []
    joints = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        shoulder, elbow, wrist = (
            by_name.get(f"{name}_{suffix}")
            for name in ("Shoulder", "Elbow", "Wrist")
        )
        if (
            shoulder is None
            or elbow is None
            or wrist is None
            or elbow.parent_path != shoulder.path
            or wrist.parent_path != elbow.path
        ):
            raise BodyArmTwistValidationError(
                "Arm twist 要求完整的 Shoulder/Elbow/Wrist Body 链"
            )
        for segment, label, start, end in (
            (BodyArmTwistSegment.UPPER, "UpperArm", shoulder, elbow),
            (BodyArmTwistSegment.LOWER, "LowerArm", elbow, wrist),
        ):
            base_name = f"AdvPy_{label}TwistBase_{suffix}"
            base_path = f"{root_path}|{base_name}"
            quaternion_name = f"AdvPy_{label}TwistProject_{suffix}"
            segments.append(
                BodyArmTwistSegmentSpec(
                    side,
                    segment,
                    base_path,
                    base_name,
                    root_path,
                    start.path,
                    end.path,
                    f"AdvPy_{label}TwistBaseFollow_{suffix}",
                    f"AdvPy_{label}TwistCompose_{suffix}",
                    f"AdvPy_{label}TwistDecompose_{suffix}",
                    quaternion_name,
                )
            )
            for index in range(1, joints_per_segment + 1):
                fraction = index / (joints_per_segment + 1)
                name = f"AdvPy_{label}Twist{index:02d}_{suffix}"
                position = tuple(
                    a + (b - a) * fraction
                    for a, b in zip(start.world_position, end.world_position)
                )
                joints.append(
                    BodyArmTwistJointSpec(
                        side,
                        segment,
                        fraction,
                        f"{base_path}|{name}",
                        name,
                        base_path,
                        start.path,
                        end.path,
                        f"AdvPy_{label}TwistPosition{index:02d}_{suffix}",
                        f"AdvPy_{label}TwistScale{index:02d}_{suffix}",
                        quaternion_name,
                        position,
                    )
                )
    return BodyArmTwistPlan(root_path, root_name, tuple(segments), tuple(joints))


def audit_body_arm_twist(
    plan: BodyArmTwistPlan,
    snapshot: BodyArmTwistSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyArmTwistIssue, ...]:
    issues = []
    if snapshot.root_path != plan.root_path:
        issues.append(BodyArmTwistIssue("root_mismatch", "Arm twist 根路径不一致"))

    expected_segments = {(spec.side, spec.segment): spec for spec in plan.segments}
    actual_segments = {(state.side, state.segment): state for state in snapshot.segments}
    if set(expected_segments) != set(actual_segments):
        issues.append(BodyArmTwistIssue("segment_set_mismatch", "Arm twist 段驱动集合不一致"))
    for key in sorted(set(expected_segments) & set(actual_segments), key=str):
        spec, state = expected_segments[key], actual_segments[key]
        checks = (
            (state.path == spec.path and state.parent_path == spec.parent_path, "segment_parent_mismatch", "Arm twist 段基座路径或父级不一致"),
            (state.constraint_name == spec.constraint_name and state.targets == (spec.start_joint,) and state.driven_path == spec.path, "segment_constraint_mismatch", "Arm twist 段基座跟随约束不一致"),
            (state.compose_name == spec.compose_name and state.rotate_source == f"{spec.end_joint}.rotate" and state.rotate_order_source == f"{spec.end_joint}.rotateOrder", "compose_mismatch", "Arm twist 局部旋转输入不一致"),
            (state.decompose_name == spec.decompose_name and state.decompose_source == f"{spec.compose_name}.outputMatrix", "decompose_mismatch", "Arm twist 四元数分解输入不一致"),
            (state.quaternion_name == spec.quaternion_name and state.quaternion_x_source == f"{spec.decompose_name}.outputQuatX" and state.quaternion_w_source == f"{spec.decompose_name}.outputQuatW", "projection_mismatch", "Arm twist 轴向四元数投影不一致"),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyArmTwistIssue(code, message, spec.path))

    expected_joints = {spec.path: spec for spec in plan.joints}
    actual_joints = {state.path: state for state in snapshot.joints}
    if set(expected_joints) != set(actual_joints):
        issues.append(BodyArmTwistIssue("joint_set_mismatch", "Arm twist 关节集合不一致"))
    for path in sorted(set(expected_joints) & set(actual_joints)):
        spec, state = expected_joints[path], actual_joints[path]
        wanted_weights = (1.0 - spec.fraction, spec.fraction)
        checks = (
            (state.side is spec.side and state.segment is spec.segment, "identity_mismatch", "Arm twist side 或 segment 不一致"),
            (state.parent_path == spec.parent_path, "parent_mismatch", "Arm twist 父级不一致"),
            (_close(state.world_position, spec.world_position, tolerance), "position_mismatch", "Arm twist 初始位置不一致"),
            (state.constraint_name == spec.constraint_name and state.targets == (spec.start_joint, spec.end_joint), "constraint_mismatch", "Arm twist 双端位置约束不一致"),
            (_close(state.weights, wanted_weights, tolerance) and state.driven_joint == spec.path, "weight_mismatch", "Arm twist 位置分布权重或目标不一致"),
            (state.multiplier_name == spec.multiplier_name and state.twist_source == f"{spec.quaternion_name}.outputRotateX", "twist_source_mismatch", "Arm twist 轴向角来源不一致"),
            (abs(state.multiplier_scale - spec.fraction) <= tolerance and state.rotate_x_source == f"{spec.multiplier_name}.output", "twist_scale_mismatch", "Arm twist 角度分配不一致"),
            (_close(state.rotate_yz, (0.0, 0.0), tolerance), "swing_leak", "Arm twist helper 含有 Y/Z swing 旋转"),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyArmTwistIssue(code, message, path))
    return tuple(issues)


def _close(left, right, tolerance):
    return len(left) == len(right) and all(
        abs(a - b) <= tolerance for a, b in zip(left, right)
    )
