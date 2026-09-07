from __future__ import annotations

from typing import Mapping

from .body_limb_controls import (
    BodyLimbControlIssue,
    BodyLimbControlValidationError,
    BodyLimbFkControlPlan,
    BodyLimbFkControlSnapshot,
    BodyLimbFkControlSpec,
    BodyLimbFkControlState,
    audit_body_limb_fk_controls,
    plan_body_limb_fk_controls,
)
from .body_skeleton import BodySkeletonSnapshot


BodyLegFkControlPlan = BodyLimbFkControlPlan
BodyLegFkControlSnapshot = BodyLimbFkControlSnapshot
BodyLegFkControlSpec = BodyLimbFkControlSpec
BodyLegFkControlState = BodyLimbFkControlState
BodyLegControlIssue = BodyLimbControlIssue
BodyLegControlValidationError = BodyLimbControlValidationError


def plan_body_leg_fk_controls(
    body: BodySkeletonSnapshot,
    *,
    radius: float = 1.75,
    driven_joint_by_source: Mapping[str, str] | None = None,
) -> BodyLegFkControlPlan:
    return plan_body_limb_fk_controls(
        body,
        limb_label="Leg",
        joint_names=("Hip", "Knee", "Ankle", "Toes"),
        radius=radius,
        driven_joint_by_source=driven_joint_by_source,
    )


def audit_body_leg_fk_controls(
    plan: BodyLegFkControlPlan,
    snapshot: BodyLegFkControlSnapshot,
    *,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
) -> tuple[BodyLegControlIssue, ...]:
    return audit_body_limb_fk_controls(
        plan,
        snapshot,
        limb_label="Leg",
        tolerance=tolerance,
        check_initial_pose=check_initial_pose,
    )
