from __future__ import annotations

from .body_limb_mechanisms import (
    BodyLimbMechanismIssue,
    BodyLimbMechanismJointSpec,
    BodyLimbMechanismJointState,
    BodyLimbMechanismPlan,
    BodyLimbMechanismRole,
    BodyLimbMechanismSnapshot,
    BodyLimbMechanismValidationError,
    audit_body_limb_mechanisms,
    plan_body_limb_mechanisms,
)
from .body_skeleton import BodySkeletonSnapshot


BodyLegMechanismIssue = BodyLimbMechanismIssue
BodyLegMechanismJointSpec = BodyLimbMechanismJointSpec
BodyLegMechanismJointState = BodyLimbMechanismJointState
BodyLegMechanismPlan = BodyLimbMechanismPlan
BodyLegMechanismRole = BodyLimbMechanismRole
BodyLegMechanismSnapshot = BodyLimbMechanismSnapshot
BodyLegMechanismValidationError = BodyLimbMechanismValidationError


def plan_body_leg_mechanisms(body: BodySkeletonSnapshot) -> BodyLegMechanismPlan:
    return plan_body_limb_mechanisms(
        body,
        limb_label="Leg",
        joint_names=("Hip", "Knee", "Ankle"),
    )


def audit_body_leg_mechanisms(
    plan: BodyLegMechanismPlan,
    snapshot: BodyLegMechanismSnapshot,
    *,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
) -> tuple[BodyLegMechanismIssue, ...]:
    return audit_body_limb_mechanisms(
        plan,
        snapshot,
        tolerance=tolerance,
        check_initial_pose=check_initial_pose,
    )
