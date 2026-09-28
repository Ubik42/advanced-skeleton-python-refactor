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
from .fit_metadata import FitJointMetadata


BodyLegFkControlPlan = BodyLimbFkControlPlan
BodyLegFkControlSnapshot = BodyLimbFkControlSnapshot
BodyLegFkControlSpec = BodyLimbFkControlSpec
BodyLegFkControlState = BodyLimbFkControlState
BodyLegControlIssue = BodyLimbControlIssue
BodyLegControlValidationError = BodyLimbControlValidationError


def terminal_toes_end_control_enabled(
    metadata: tuple[FitJointMetadata, ...],
    *,
    use_offset_parent_matrix: bool = False,
) -> bool:
    """Read the end-joint Control switch, including Tweaker's implicit Control."""
    if type(use_offset_parent_matrix) is not bool:
        raise BodyLegControlValidationError("ToesEnd OPM 开关无效")
    if not isinstance(metadata, tuple) or any(
            not isinstance(item, FitJointMetadata) for item in metadata):
        raise BodyLegControlValidationError("Fit 末端控制元数据无效")
    terminal = tuple(item for item in metadata
                     if item.joint.rsplit("|", 1)[-1]
                     .rsplit(":", 1)[-1] == "ToesEnd")
    if len(terminal) > 1:
        raise BodyLegControlValidationError("Fit ToesEnd 元数据重复")
    return bool(terminal and (terminal[0].control
                              or (use_offset_parent_matrix
                                  and terminal[0].tweaker_control)))


def plan_body_leg_fk_controls(
    body: BodySkeletonSnapshot,
    *,
    radius: float = 1.5,
    driven_joint_by_source: Mapping[str, str] | None = None,
    sub_controllers: bool = False,
    extra_controllers: bool = False,
    terminal_toes_end_control: bool = False,
    allow_part_parents: bool = False,
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
        allow_part_parents=allow_part_parents,
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
