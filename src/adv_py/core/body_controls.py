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


BodyArmFkControlPlan = BodyLimbFkControlPlan
BodyArmFkControlSnapshot = BodyLimbFkControlSnapshot
BodyArmFkControlSpec = BodyLimbFkControlSpec
BodyArmFkControlState = BodyLimbFkControlState
BodyControlIssue = BodyLimbControlIssue
BodyControlValidationError = BodyLimbControlValidationError


def plan_body_arm_fk_controls(
    body: BodySkeletonSnapshot,
    *,
    radius: float = 1.5,
    driven_joint_by_source: Mapping[str, str] | None = None,
    sub_controllers: bool = False,
    extra_controllers: bool = False,
    allow_part_parents: bool = False,
    aim_joint_names: frozenset[str] = frozenset(),
    use_offset_parent_matrix: bool = False,
    fkx_joint_names: frozenset[str] | None = None,
    point_control_names: frozenset[str] | None = None,
) -> BodyArmFkControlPlan:
    return plan_body_limb_fk_controls(
        body,
        limb_label="Arm",
        joint_names=("Shoulder", "Elbow", "Wrist"),
        radius=radius,
        driven_joint_by_source=driven_joint_by_source,
        sub_controllers=sub_controllers,
        extra_controllers=extra_controllers,
        root_parent_path=("|Group|MotionSystem|FKSystem"
                          if body.root.startswith("|Group|DeformationSystem|")
                          else None),
        allow_part_parents=allow_part_parents,
        aim_joint_names=aim_joint_names,
        use_offset_parent_matrix=use_offset_parent_matrix,
        fkx_joint_names=fkx_joint_names,
        point_control_names=point_control_names,
    )


def audit_body_arm_fk_controls(
    plan: BodyArmFkControlPlan,
    snapshot: BodyArmFkControlSnapshot,
    *,
    tolerance: float = 1e-4,
    check_initial_pose: bool = True,
) -> tuple[BodyControlIssue, ...]:
    return audit_body_limb_fk_controls(
        plan,
        snapshot,
        limb_label="Arm",
        tolerance=tolerance,
        check_initial_pose=check_initial_pose,
    )
