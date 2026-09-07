from __future__ import annotations

from .core import ConstraintSpec, NodeSpec, RigPlan, translation_matrix


def two_joint_plan() -> RigPlan:
    """Small, self-generated acceptance case shared by every host adapter."""

    return RigPlan(
        name="两节跨DCC骨架",
        nodes=(
            NodeSpec(
                key="root",
                name="PortableRoot_JNT",
                kind="joint",
                world_matrix=translation_matrix(0.0, 0.0, 0.0),
            ),
            NodeSpec(
                key="tip",
                name="PortableTip_JNT",
                kind="joint",
                parent="root",
                world_matrix=translation_matrix(0.0, 2.0, 0.0),
            ),
            NodeSpec(
                key="root_ctrl",
                name="PortableRoot_CTRL",
                kind="control",
                world_matrix=translation_matrix(0.0, 0.0, 0.0),
            ),
            NodeSpec(
                key="tip_ctrl",
                name="PortableTip_CTRL",
                kind="control",
                world_matrix=translation_matrix(0.0, 2.0, 0.0),
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
