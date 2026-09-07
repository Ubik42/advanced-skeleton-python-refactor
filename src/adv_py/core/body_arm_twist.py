from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import FitBuildSide


Vector3 = tuple[float, float, float]


class BodyArmTwistSegment(str, Enum):
    UPPER = "upper"
    LOWER = "lower"


class BodyArmTwistValidationError(ValueError):
    pass


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
    world_position: Vector3


@dataclass(frozen=True, slots=True)
class BodyArmTwistPlan:
    root_path: str
    root_name: str
    joints: tuple[BodyArmTwistJointSpec, ...]


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
    interpolation_type: int


@dataclass(frozen=True, slots=True)
class BodyArmTwistSnapshot:
    root_path: str
    joints: tuple[BodyArmTwistJointState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmTwistIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_arm_twist(
    body: BodySkeletonSnapshot,
    *,
    joints_per_segment: int = 2,
) -> BodyArmTwistPlan:
    if isinstance(joints_per_segment, bool) or not isinstance(joints_per_segment, int) or not 1 <= joints_per_segment <= 8:
        raise BodyArmTwistValidationError("Arm twist 每段关节数量必须位于 1 到 8")
    by_name = {joint.name: joint for joint in body.joints}
    root_name = "AdvPy_ArmTwistJoints"
    root_path = f"|{root_name}"
    specs = []
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        shoulder, elbow, wrist = (by_name.get(f"{name}_{suffix}") for name in ("Shoulder", "Elbow", "Wrist"))
        if shoulder is None or elbow is None or wrist is None or elbow.parent_path != shoulder.path or wrist.parent_path != elbow.path:
            raise BodyArmTwistValidationError("Arm twist 要求完整的 Shoulder/Elbow/Wrist Body 链")
        for segment, label, start, end in (
            (BodyArmTwistSegment.UPPER, "UpperArm", shoulder, elbow),
            (BodyArmTwistSegment.LOWER, "LowerArm", elbow, wrist),
        ):
            for index in range(1, joints_per_segment + 1):
                fraction = index / (joints_per_segment + 1)
                name = f"AdvPy_{label}Twist{index:02d}_{suffix}"
                position = tuple(a + (b - a) * fraction for a, b in zip(start.world_position, end.world_position))
                specs.append(BodyArmTwistJointSpec(
                    side,
                    segment,
                    fraction,
                    f"{root_path}|{name}",
                    name,
                    root_path,
                    start.path,
                    end.path,
                    f"AdvPy_{label}TwistDrive{index:02d}_{suffix}",
                    position,
                ))
    return BodyArmTwistPlan(root_path, root_name, tuple(specs))


def audit_body_arm_twist(
    plan: BodyArmTwistPlan,
    snapshot: BodyArmTwistSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyArmTwistIssue, ...]:
    issues = []
    if snapshot.root_path != plan.root_path:
        issues.append(BodyArmTwistIssue("root_mismatch", "Arm twist 根路径不一致"))
    expected = {spec.path: spec for spec in plan.joints}
    actual = {state.path: state for state in snapshot.joints}
    if set(expected) != set(actual):
        issues.append(BodyArmTwistIssue("joint_set_mismatch", "Arm twist 关节集合不一致"))
    for path in sorted(set(expected) & set(actual)):
        spec, state = expected[path], actual[path]
        wanted_weights = (1.0 - spec.fraction, spec.fraction)
        checks = (
            (state.side is spec.side and state.segment is spec.segment, "identity_mismatch", "Arm twist side 或 segment 不一致"),
            (state.parent_path == spec.parent_path, "parent_mismatch", "Arm twist 父级不一致"),
            (_close(state.world_position, spec.world_position, tolerance), "position_mismatch", "Arm twist 初始位置不一致"),
            (state.constraint_name == spec.constraint_name and state.targets == (spec.start_joint, spec.end_joint), "constraint_mismatch", "Arm twist 双端约束不一致"),
            (_close(state.weights, wanted_weights, tolerance), "weight_mismatch", "Arm twist 分布权重不一致"),
            (state.driven_joint == spec.path and state.interpolation_type == 2, "drive_mismatch", "Arm twist 驱动目标或插值模式不一致"),
        )
        for passed, code, message in checks:
            if not passed:
                issues.append(BodyArmTwistIssue(code, message, path))
    return tuple(issues)


def _close(left, right, tolerance):
    return len(left) == len(right) and all(abs(a - b) <= tolerance for a, b in zip(left, right))
