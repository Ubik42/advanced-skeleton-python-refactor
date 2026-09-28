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


BodyArmMechanismIssue = BodyLimbMechanismIssue
BodyArmMechanismJointSpec = BodyLimbMechanismJointSpec
BodyArmMechanismJointState = BodyLimbMechanismJointState
BodyArmMechanismPlan = BodyLimbMechanismPlan
BodyArmMechanismRole = BodyLimbMechanismRole
BodyArmMechanismSnapshot = BodyLimbMechanismSnapshot
BodyArmMechanismValidationError = BodyLimbMechanismValidationError


def plan_body_arm_mechanisms(
    body: BodySkeletonSnapshot, *, allow_part_parents: bool = False,
) -> BodyArmMechanismPlan:
    return plan_body_limb_mechanisms(
        body,
        limb_label="Arm",
        joint_names=("Shoulder", "Elbow", "Wrist"),
        allow_part_parents=allow_part_parents,
    )


def audit_body_arm_mechanisms(
    plan: BodyArmMechanismPlan,
    snapshot: BodyArmMechanismSnapshot,
    *,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
) -> tuple[BodyArmMechanismIssue, ...]:
    return audit_body_limb_mechanisms(
        plan,
        snapshot,
        tolerance=tolerance,
        check_initial_pose=check_initial_pose,
    )
