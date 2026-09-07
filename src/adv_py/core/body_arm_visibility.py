from __future__ import annotations

from .body_arm_blend import BodyArmBlendPlan
from .body_arm_ik import BodyArmIkPlan
from .body_controls import BodyArmFkControlPlan
from .body_limb_visibility import (
    BodyLimbVisibilityIssue,
    BodyLimbVisibilityPlan,
    BodyLimbVisibilitySideSpec,
    BodyLimbVisibilitySideState,
    BodyLimbVisibilitySnapshot,
    audit_body_limb_visibility,
    plan_body_limb_visibility,
)

BodyArmVisibilityIssue = BodyLimbVisibilityIssue
BodyArmVisibilityPlan = BodyLimbVisibilityPlan
BodyArmVisibilitySideSpec = BodyLimbVisibilitySideSpec
BodyArmVisibilitySideState = BodyLimbVisibilitySideState
BodyArmVisibilitySnapshot = BodyLimbVisibilitySnapshot


def plan_body_arm_visibility(
    fk_controls: BodyArmFkControlPlan,
    ik: BodyArmIkPlan,
    blend: BodyArmBlendPlan,
) -> BodyArmVisibilityPlan:
    offsets = {
        limb.side: (limb.wrist_offset_path, limb.pole_offset_path)
        for limb in ik.limbs
    }
    return plan_body_limb_visibility(
        fk_controls, blend, offsets, limb_label="Arm"
    )


def audit_body_arm_visibility(
    plan: BodyArmVisibilityPlan,
    snapshot: BodyArmVisibilitySnapshot,
) -> tuple[BodyArmVisibilityIssue, ...]:
    return audit_body_limb_visibility(plan, snapshot, limb_label="Arm")
