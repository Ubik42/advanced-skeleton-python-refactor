from __future__ import annotations

from .body_leg_mechanisms import BodyLegMechanismPlan
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


BodyLegBlendIssue = BodyLimbBlendIssue
BodyLegBlendJointSpec = BodyLimbBlendJointSpec
BodyLegBlendJointState = BodyLimbBlendJointState
BodyLegBlendPlan = BodyLimbBlendPlan
BodyLegBlendSideSpec = BodyLimbBlendSideSpec
BodyLegBlendSideState = BodyLimbBlendSideState
BodyLegBlendSnapshot = BodyLimbBlendSnapshot
BodyLegBlendValidationError = BodyLimbBlendValidationError


def plan_body_leg_blend(
    body: BodySkeletonSnapshot,
    mechanisms: BodyLegMechanismPlan,
) -> BodyLegBlendPlan:
    return plan_body_limb_blend(
        body,
        mechanisms,
        limb_label="Leg",
        joint_names=("Hip", "Knee", "Ankle"),
        translated_joint_names=("Knee", "Ankle"),
    )


def audit_body_leg_blend(
    plan: BodyLegBlendPlan,
    snapshot: BodyLegBlendSnapshot,
    *,
    expected_attribute_value: float | None = 0.0,
) -> tuple[BodyLegBlendIssue, ...]:
    return audit_body_limb_blend(
        plan,
        snapshot,
        limb_label="Leg",
        expected_attribute_value=expected_attribute_value,
    )
