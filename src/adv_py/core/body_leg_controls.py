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
    radius: float = 1.5,
    driven_joint_by_source: Mapping[str, str] | None = None,
    sub_controllers: bool = False,
    extra_controllers: bool = False,
    terminal_toes_end_control: bool = False,
) -> BodyLegFkControlPlan:
    if type(terminal_toes_end_control) is not bool:
        raise BodyLegControlValidationError("ToesEnd Control 开关无效")
    return plan_body_limb_fk_controls(
        body,
        limb_label="Leg",
        joint_names=(("Hip", "Knee", "Ankle", "Toes", "ToesEnd")
                     if terminal_toes_end_control else
                     ("Hip", "Knee", "Ankle", "Toes")),
        radius=radius,
        driven_joint_by_source=driven_joint_by_source,
        sub_controllers=sub_controllers,
        extra_controllers=extra_controllers,
        root_parent_path=("|Group|MotionSystem|FKSystem"
                          if body.root.startswith("|Group|DeformationSystem|")
                          else None),
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
