from __future__ import annotations

from .core import (
    ConstraintSpec,
    NodeSpec,
    RigPlan,
    multiply,
    rotation_y_matrix,
    rotation_z_matrix,
    with_translation,
)


def _joint_matrix(x: float, y: float, z: float, *, aim_z: float, roll_y: float):
    orientation = multiply(rotation_z_matrix(aim_z), rotation_y_matrix(roll_y))
    return with_translation(orientation, x, y, z)


def two_joint_plan() -> RigPlan:
    """Small, self-generated acceptance case shared by every host adapter."""

    return RigPlan(
        name="两节跨DCC骨架",
        nodes=(
            NodeSpec(
                key="root",
                name="PortableRoot_JNT",
                kind="joint",
                world_matrix=_joint_matrix(0.0, 0.0, 0.0, aim_z=30.0, roll_y=20.0),
            ),
            NodeSpec(
                key="tip",
                name="PortableTip_JNT",
                kind="joint",
                parent="root",
                world_matrix=_joint_matrix(0.0, 2.0, 0.0, aim_z=-15.0, roll_y=-10.0),
            ),
            NodeSpec(
                key="root_ctrl",
                name="PortableRoot_CTRL",
                kind="control",
                world_matrix=_joint_matrix(0.0, 0.0, 0.0, aim_z=30.0, roll_y=20.0),
            ),
            NodeSpec(
                key="tip_ctrl",
                name="PortableTip_CTRL",
                kind="control",
                world_matrix=_joint_matrix(0.0, 2.0, 0.0, aim_z=-15.0, roll_y=-10.0),
            ),
        ),
        constraints=(
            ConstraintSpec(
                kind="parent",
                sources=("root_ctrl",),
                target="root",
                maintain_offset=False,
            ),
            ConstraintSpec(
                kind="orient",
                sources=("tip_ctrl",),
                target="tip",
                maintain_offset=False,
            ),
        ),
    )
