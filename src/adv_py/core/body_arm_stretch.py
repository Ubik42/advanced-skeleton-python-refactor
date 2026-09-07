from __future__ import annotations

from .body_arm_ik import BodyArmIkPlan
from .body_arm_mechanisms import BodyArmMechanismPlan
from .body_limb_stretch import (
    BodyLimbStretchIssue,
    BodyLimbStretchPlan,
    BodyLimbStretchSideSpec,
    BodyLimbStretchSideState,
    BodyLimbStretchSnapshot,
    BodyLimbStretchValidationError,
    audit_body_limb_stretch,
    compensated_stretch_ratio,
    plan_body_limb_stretch,
)


BodyArmStretchIssue = BodyLimbStretchIssue
BodyArmStretchPlan = BodyLimbStretchPlan
BodyArmStretchSideSpec = BodyLimbStretchSideSpec
BodyArmStretchSideState = BodyLimbStretchSideState
BodyArmStretchSnapshot = BodyLimbStretchSnapshot
BodyArmStretchValidationError = BodyLimbStretchValidationError


def plan_body_arm_stretch(
    mechanisms: BodyArmMechanismPlan,
    ik: BodyArmIkPlan,
    *,
    alignment_tolerance: float = 1e-4,
) -> BodyArmStretchPlan:
    targets = {spec.side: spec.wrist_control_path for spec in ik.limbs}
    return plan_body_limb_stretch(
        mechanisms,
        targets,
        limb_label="Arm",
        alignment_tolerance=alignment_tolerance,
    )


def audit_body_arm_stretch(
    plan: BodyArmStretchPlan,
    snapshot: BodyArmStretchSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyArmStretchIssue, ...]:
    return audit_body_limb_stretch(plan, snapshot, tolerance=tolerance)
