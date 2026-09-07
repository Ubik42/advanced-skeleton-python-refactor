from __future__ import annotations

from .body_arm_mechanisms import BodyArmMechanismPlan
from .body_limb_blend import (
    BodyLimbBlendIssue,
    BodyLimbBlendJointSpec,
    BodyLimbBlendJointState,
    BodyLimbBlendPlan,
    BodyLimbBlendSideSpec,
    BodyLimbBlendSideState,
    BodyLimbBlendSnapshot,
    BodyLimbBlendValidationError,
    audit_body_limb_blend,
    plan_body_limb_blend,
)
from .body_skeleton import BodySkeletonSnapshot


BodyArmBlendIssue = BodyLimbBlendIssue
BodyArmBlendJointSpec = BodyLimbBlendJointSpec
BodyArmBlendJointState = BodyLimbBlendJointState
BodyArmBlendPlan = BodyLimbBlendPlan
BodyArmBlendSideSpec = BodyLimbBlendSideSpec
BodyArmBlendSideState = BodyLimbBlendSideState
BodyArmBlendSnapshot = BodyLimbBlendSnapshot
BodyArmBlendValidationError = BodyLimbBlendValidationError


def plan_body_arm_blend(
    body: BodySkeletonSnapshot,
    mechanisms: BodyArmMechanismPlan,
) -> BodyArmBlendPlan:
    return plan_body_limb_blend(
        body,
        mechanisms,
        limb_label="Arm",
        joint_names=("Shoulder", "Elbow", "Wrist"),
        translated_joint_names=("Elbow", "Wrist"),
    )


def audit_body_arm_blend(
    plan: BodyArmBlendPlan,
    snapshot: BodyArmBlendSnapshot,
    *,
    expected_attribute_value: float | None = 0.0,
) -> tuple[BodyArmBlendIssue, ...]:
    return audit_body_limb_blend(
        plan,
        snapshot,
        limb_label="Arm",
        expected_attribute_value=expected_attribute_value,
    )
