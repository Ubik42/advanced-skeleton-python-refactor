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


BodyLegTwistIssue = BodyLimbTwistIssue
BodyLegTwistJointSpec = BodyLimbTwistJointSpec
BodyLegTwistJointState = BodyLimbTwistJointState
BodyLegTwistPlan = BodyLimbTwistPlan
BodyLegTwistSegment = BodyLimbTwistSegment
BodyLegTwistSegmentSpec = BodyLimbTwistSegmentSpec
BodyLegTwistSegmentState = BodyLimbTwistSegmentState
BodyLegTwistSnapshot = BodyLimbTwistSnapshot
BodyLegTwistValidationError = BodyLimbTwistValidationError


def plan_body_leg_twist(
    body: BodySkeletonSnapshot,
    *,
    joints_per_segment: int = 2,
) -> BodyLegTwistPlan:
    return plan_body_limb_twist(
        body,
        limb_label="Leg",
        joint_names=("Hip", "Knee", "Ankle"),
        segment_labels=("UpperLeg", "LowerLeg"),
        joints_per_segment=joints_per_segment,
    )


def audit_body_leg_twist(
    plan: BodyLegTwistPlan,
    snapshot: BodyLegTwistSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyLegTwistIssue, ...]:
    return audit_body_limb_twist(plan, snapshot, tolerance=tolerance)
