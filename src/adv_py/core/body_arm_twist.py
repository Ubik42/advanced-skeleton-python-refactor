from __future__ import annotations

from .body_limb_twist import (
    BodyLimbTwistIssue,
    BodyLimbTwistJointSpec,
    BodyLimbTwistJointState,
    BodyLimbTwistPlan,
    BodyLimbTwistSegment,
    BodyLimbTwistSegmentSpec,
    BodyLimbTwistSegmentState,
    BodyLimbTwistSnapshot,
    BodyLimbTwistValidationError,
    audit_body_limb_twist,
    plan_body_limb_twist,
    project_twist_quaternion,
    twist_angle,
)
from .body_skeleton import BodySkeletonSnapshot


BodyArmTwistIssue = BodyLimbTwistIssue
BodyArmTwistJointSpec = BodyLimbTwistJointSpec
BodyArmTwistJointState = BodyLimbTwistJointState
BodyArmTwistPlan = BodyLimbTwistPlan
BodyArmTwistSegment = BodyLimbTwistSegment
BodyArmTwistSegmentSpec = BodyLimbTwistSegmentSpec
BodyArmTwistSegmentState = BodyLimbTwistSegmentState
BodyArmTwistSnapshot = BodyLimbTwistSnapshot
BodyArmTwistValidationError = BodyLimbTwistValidationError


def project_twist_quaternion_x(
    quaternion: tuple[float, float, float, float],
    *,
    tolerance: float = 1e-8,
) -> tuple[float, float, float, float]:
    """Backward-compatible Arm helper for the historic local-X contract."""

    return project_twist_quaternion(quaternion, "X", tolerance=tolerance)


def twist_angle_x(quaternion: tuple[float, float, float, float]) -> float:
    return twist_angle(quaternion, "X")


def plan_body_arm_twist(
    body: BodySkeletonSnapshot,
    *,
    joints_per_segment: int = 2,
) -> BodyArmTwistPlan:
    return plan_body_limb_twist(
        body,
        limb_label="Arm",
        joint_names=("Shoulder", "Elbow", "Wrist"),
        segment_labels=("UpperArm", "LowerArm"),
        joints_per_segment=joints_per_segment,
    )


def audit_body_arm_twist(
    plan: BodyArmTwistPlan,
    snapshot: BodyArmTwistSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyArmTwistIssue, ...]:
    return audit_body_limb_twist(plan, snapshot, tolerance=tolerance)
