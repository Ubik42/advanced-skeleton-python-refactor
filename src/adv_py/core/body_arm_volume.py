from __future__ import annotations

from .body_arm_blend import BodyArmBlendPlan
from .body_arm_stretch import BodyArmStretchPlan
from .body_arm_twist import BodyArmTwistPlan
from .body_limb_volume import (
    BodyLimbVolumeIssue,
    BodyLimbVolumePlan,
    BodyLimbVolumeSideSpec,
    BodyLimbVolumeSideState,
    BodyLimbVolumeSnapshot,
    BodyLimbVolumeValidationError,
    audit_body_limb_volume,
    plan_body_limb_volume,
    volume_preservation_scale,
)


BodyArmVolumeIssue = BodyLimbVolumeIssue
BodyArmVolumePlan = BodyLimbVolumePlan
BodyArmVolumeSideSpec = BodyLimbVolumeSideSpec
BodyArmVolumeSideState = BodyLimbVolumeSideState
BodyArmVolumeSnapshot = BodyLimbVolumeSnapshot
BodyArmVolumeValidationError = BodyLimbVolumeValidationError


def plan_body_arm_volume(
    stretch: BodyArmStretchPlan,
    twist: BodyArmTwistPlan,
    blend: BodyArmBlendPlan,
) -> BodyArmVolumePlan:
    return plan_body_limb_volume(
        stretch,
        twist,
        blend,
        limb_label="Arm",
    )


def audit_body_arm_volume(
    plan: BodyArmVolumePlan,
    snapshot: BodyArmVolumeSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyArmVolumeIssue, ...]:
    return audit_body_limb_volume(plan, snapshot, tolerance=tolerance)
