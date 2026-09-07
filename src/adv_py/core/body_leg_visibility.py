from __future__ import annotations

from .body_leg_blend import BodyLegBlendPlan
from .body_leg_controls import BodyLegFkControlPlan
from .body_leg_ik import BodyLegIkPlan
from .body_limb_visibility import (
    BodyLimbVisibilityInputState,
    BodyLimbVisibilityIssue,
    BodyLimbVisibilityPlan,
    BodyLimbVisibilitySideSpec,
    BodyLimbVisibilitySideState,
    BodyLimbVisibilitySnapshot,
    audit_body_limb_visibility,
    audit_body_limb_visibility_input,
    plan_body_limb_visibility,
)

BodyLegVisibilityInputState = BodyLimbVisibilityInputState
BodyLegVisibilityIssue = BodyLimbVisibilityIssue
BodyLegVisibilityPlan = BodyLimbVisibilityPlan
BodyLegVisibilitySideSpec = BodyLimbVisibilitySideSpec
BodyLegVisibilitySideState = BodyLimbVisibilitySideState
BodyLegVisibilitySnapshot = BodyLimbVisibilitySnapshot


def plan_body_leg_visibility(
    fk_controls: BodyLegFkControlPlan,
    ik: BodyLegIkPlan,
    blend: BodyLegBlendPlan,
) -> BodyLegVisibilityPlan:
    offsets = {
        limb.side: (limb.ankle_offset_path, limb.pole_offset_path)
        for limb in ik.limbs
    }
    return plan_body_limb_visibility(
        fk_controls, blend, offsets, limb_label="Leg"
    )


def audit_body_leg_visibility_input(
    plan: BodyLegVisibilityPlan,
    state: BodyLegVisibilityInputState,
) -> tuple[BodyLegVisibilityIssue, ...]:
    return audit_body_limb_visibility_input(plan, state, limb_label="Leg")


def audit_body_leg_visibility(
    plan: BodyLegVisibilityPlan,
    snapshot: BodyLegVisibilitySnapshot,
) -> tuple[BodyLegVisibilityIssue, ...]:
    return audit_body_limb_visibility(plan, snapshot, limb_label="Leg")
