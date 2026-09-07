from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import atan2, isfinite, sqrt

from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import FitBuildSide


Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]


class BodyLimbTwistSegment(str, Enum):
    UPPER = "upper"
    LOWER = "lower"


class BodyLimbTwistValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyLimbTwistSegmentSpec:
    side: FitBuildSide
    segment: BodyLimbTwistSegment
    path: str
    name: str
    parent_path: str
    start_joint: str
    end_joint: str
    constraint_name: str
    compose_name: str
    decompose_name: str
    quaternion_name: str
    axis: str = "X"


@dataclass(frozen=True, slots=True)
class BodyLimbTwistJointSpec:
    side: FitBuildSide
    segment: BodyLimbTwistSegment
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
    axis: str = "X"


@dataclass(frozen=True, slots=True)
class BodyLimbTwistPlan:
    root_path: str
    root_name: str
    segments: tuple[BodyLimbTwistSegmentSpec, ...]
    joints: tuple[BodyLimbTwistJointSpec, ...]
    limb_label: str = "Arm"


@dataclass(frozen=True, slots=True)
class BodyLimbTwistSegmentState:
    side: FitBuildSide
    segment: BodyLimbTwistSegment
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
    quaternion_axis_source: str | None
    quaternion_w_source: str | None
    axis: str


@dataclass(frozen=True, slots=True)
class BodyLimbTwistJointState:
    side: FitBuildSide
    segment: BodyLimbTwistSegment
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
    rotate_axis_source: str | None
    orthogonal_rotations: tuple[float, float]
    axis: str


@dataclass(frozen=True, slots=True)
class BodyLimbTwistSnapshot:
    root_path: str
    segments: tuple[BodyLimbTwistSegmentState, ...]
    joints: tuple[BodyLimbTwistJointState, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbTwistIssue:
    code: str
    message: str
    subject: str | None = None


def project_twist_quaternion(
    quaternion: Quaternion,
    axis: str,
    *,
    tolerance: float = 1e-8,
) -> Quaternion:
    """Project a quaternion onto one local principal axis."""

    if (
        axis not in "XYZ"
        or len(quaternion) != 4
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(value)
            for value in quaternion
        )
        or isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not isfinite(tolerance)
        or tolerance <= 0.0
    ):
        raise BodyLimbTwistValidationError("Limb twist 四元数、主轴或容差无效")
    values = [float(value) for value in quaternion]
    index = "XYZ".index(axis)
    component = values[index]
    w = values[3]
    magnitude = sqrt(component * component + w * w)
    if magnitude <= tolerance:
        return (0.0, 0.0, 0.0, 1.0)
    component, w = component / magnitude, w / magnitude
    if w < 0.0:
        component, w = -component, -w
    projected = [0.0, 0.0, 0.0, w]
    projected[index] = component
    return tuple(projected)


def twist_angle(quaternion: Quaternion, axis: str) -> float:
    projected = project_twist_quaternion(quaternion, axis)
    return 2.0 * atan2(projected["XYZ".index(axis)], projected[3])


def plan_body_limb_twist(
    body: BodySkeletonSnapshot,
    *,
    limb_label: str,
    joint_names: tuple[str, str, str],
    segment_labels: tuple[str, str],
    joints_per_segment: int = 2,
    alignment_tolerance: float = 1e-4,
) -> BodyLimbTwistPlan:
    if (
        not isinstance(limb_label, str)
        or not limb_label.isalpha()
        or len(joint_names) != 3
        or len(set(joint_names)) != 3
        or any(not name.isalpha() for name in joint_names)
        or len(segment_labels) != 2
        or len(set(segment_labels)) != 2
        or any(not label.isalpha() for label in segment_labels)
        or isinstance(joints_per_segment, bool)
        or not isinstance(joints_per_segment, int)
        or not 1 <= joints_per_segment <= 8
        or isinstance(alignment_tolerance, bool)
        or not isinstance(alignment_tolerance, (int, float))
        or not isfinite(float(alignment_tolerance))
        or alignment_tolerance < 0.0
    ):
        raise BodyLimbTwistValidationError(f"{limb_label} twist 定义无效")
    by_name = {joint.name: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise BodyLimbTwistValidationError("Body joint 名称不唯一")
    root_name = f"AdvPy_{limb_label}TwistJoints"
    root_path = f"|{root_name}"
    segments = []
    joints = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        chain = tuple(
            by_name.get(f"{name}_{suffix}") for name in joint_names
        )
        if (
            any(joint is None for joint in chain)
            or chain[1].parent_path != chain[0].path
            or chain[2].parent_path != chain[1].path
            or any(joint.side is not side for joint in chain)
        ):
            raise BodyLimbTwistValidationError(
                f"{limb_label} twist 要求完整的 {'/'.join(joint_names)} Body 链"
            )
        for segment, label, start, end in (
            (BodyLimbTwistSegment.UPPER, segment_labels[0], chain[0], chain[1]),
            (BodyLimbTwistSegment.LOWER, segment_labels[1], chain[1], chain[2]),
        ):
            axis = _principal_axis(start, end, float(alignment_tolerance))
            base_name = f"AdvPy_{label}TwistBase_{suffix}"
            base_path = f"{root_path}|{base_name}"
            quaternion_name = f"AdvPy_{label}TwistProject_{suffix}"
            segments.append(BodyLimbTwistSegmentSpec(
                side=side,
                segment=segment,
                path=base_path,
                name=base_name,
                parent_path=root_path,
                start_joint=start.path,
                end_joint=end.path,
                constraint_name=f"AdvPy_{label}TwistBaseFollow_{suffix}",
                compose_name=f"AdvPy_{label}TwistCompose_{suffix}",
                decompose_name=f"AdvPy_{label}TwistDecompose_{suffix}",
                quaternion_name=quaternion_name,
                axis=axis,
            ))
            for index in range(1, joints_per_segment + 1):
                fraction = index / (joints_per_segment + 1)
                name = f"AdvPy_{label}Twist{index:02d}_{suffix}"
                position = tuple(
                    start_value + (end_value - start_value) * fraction
                    for start_value, end_value in zip(
                        start.world_position, end.world_position
                    )
                )
                joints.append(BodyLimbTwistJointSpec(
                    side=side,
                    segment=segment,
                    fraction=fraction,
                    path=f"{base_path}|{name}",
                    name=name,
                    parent_path=base_path,
                    start_joint=start.path,
                    end_joint=end.path,
                    constraint_name=f"AdvPy_{label}TwistPosition{index:02d}_{suffix}",
                    multiplier_name=f"AdvPy_{label}TwistScale{index:02d}_{suffix}",
                    quaternion_name=quaternion_name,
                    world_position=position,
                    axis=axis,
                ))
    return BodyLimbTwistPlan(
        root_path,
        root_name,
        tuple(segments),
        tuple(joints),
        limb_label,
    )


def audit_body_limb_twist(
    plan: BodyLimbTwistPlan,
    snapshot: BodyLimbTwistSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyLimbTwistIssue, ...]:
    label = plan.limb_label
    issues = []
    if snapshot.root_path != plan.root_path:
        issues.append(BodyLimbTwistIssue(
            "root_mismatch", f"{label} twist 根路径不一致"
        ))

    expected_segments = {(spec.side, spec.segment): spec for spec in plan.segments}
    actual_segments = {(state.side, state.segment): state for state in snapshot.segments}
    if set(expected_segments) != set(actual_segments):
        issues.append(BodyLimbTwistIssue(
            "segment_set_mismatch", f"{label} twist 段驱动集合不一致"
        ))
    for key in sorted(set(expected_segments) & set(actual_segments), key=str):
        spec, state = expected_segments[key], actual_segments[key]
        checks = (
            (state.path == spec.path and state.parent_path == spec.parent_path, "segment_parent_mismatch", f"{label} twist 段基座路径或父级不一致"),
            (state.constraint_name == spec.constraint_name and state.targets == (spec.start_joint,) and state.driven_path == spec.path, "segment_constraint_mismatch", f"{label} twist 段基座跟随约束不一致"),
            (state.compose_name == spec.compose_name and state.rotate_source == f"{spec.end_joint}.rotate" and state.rotate_order_source == f"{spec.end_joint}.rotateOrder", "compose_mismatch", f"{label} twist 局部旋转输入不一致"),
            (state.decompose_name == spec.decompose_name and state.decompose_source == f"{spec.compose_name}.outputMatrix", "decompose_mismatch", f"{label} twist 四元数分解输入不一致"),
            (state.axis == spec.axis and state.quaternion_name == spec.quaternion_name and state.quaternion_axis_source == f"{spec.decompose_name}.outputQuat{spec.axis}" and state.quaternion_w_source == f"{spec.decompose_name}.outputQuatW", "projection_mismatch", f"{label} twist 轴向四元数投影不一致"),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyLimbTwistIssue(code, message, spec.path))

    expected_joints = {spec.path: spec for spec in plan.joints}
    actual_joints = {state.path: state for state in snapshot.joints}
    if set(expected_joints) != set(actual_joints):
        issues.append(BodyLimbTwistIssue(
            "joint_set_mismatch", f"{label} twist 关节集合不一致"
        ))
    for path in sorted(set(expected_joints) & set(actual_joints)):
        spec, state = expected_joints[path], actual_joints[path]
        wanted_weights = (1.0 - spec.fraction, spec.fraction)
        checks = (
            (state.side is spec.side and state.segment is spec.segment and state.axis == spec.axis, "identity_mismatch", f"{label} twist side、segment 或主轴不一致"),
            (state.parent_path == spec.parent_path, "parent_mismatch", f"{label} twist 父级不一致"),
            (_close(state.world_position, spec.world_position, tolerance), "position_mismatch", f"{label} twist 初始位置不一致"),
            (state.constraint_name == spec.constraint_name and state.targets == (spec.start_joint, spec.end_joint), "constraint_mismatch", f"{label} twist 双端位置约束不一致"),
            (_close(state.weights, wanted_weights, tolerance) and state.driven_joint == spec.path, "weight_mismatch", f"{label} twist 位置分布权重或目标不一致"),
            (state.multiplier_name == spec.multiplier_name and state.twist_source == f"{spec.quaternion_name}.outputRotate{spec.axis}", "twist_source_mismatch", f"{label} twist 轴向角来源不一致"),
            (abs(state.multiplier_scale - spec.fraction) <= tolerance and state.rotate_axis_source == f"{spec.multiplier_name}.output", "twist_scale_mismatch", f"{label} twist 角度分配不一致"),
            (_close(state.orthogonal_rotations, (0.0, 0.0), tolerance), "swing_leak", f"{label} twist helper 含有正交轴 swing 旋转"),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyLimbTwistIssue(code, message, path))
    return tuple(issues)


def _principal_axis(start, end, tolerance: float) -> str:
    delta = tuple(
        end_value - start_value
        for start_value, end_value in zip(
            start.world_position, end.world_position
        )
    )
    length = sqrt(sum(value * value for value in delta))
    projections = tuple(
        sum(value * component for value, component in zip(delta, axis))
        for axis in start.world_axes
    )
    index = max(range(3), key=lambda value: abs(projections[value]))
    if (
        not isfinite(length)
        or not isfinite(projections[index])
        or length <= 1e-6
        or abs(abs(projections[index]) - length) > tolerance
    ):
        raise BodyLimbTwistValidationError(
            "Limb twist 要求每段沿一个明确的关节本地主轴"
        )
    return "XYZ"[index]


def _close(left, right, tolerance):
    return len(left) == len(right) and all(
        abs(a - b) <= tolerance for a, b in zip(left, right)
    )
