from __future__ import annotations

from .core import (
    ConstraintSpec,
    LimbSpec,
    NodeSpec,
    RigPlan,
    frame_from_y,
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


def ik_fk_limb_plan() -> RigPlan:
    """Self-generated bent three-joint limb with FK, IK and bind chains."""

    positions = ((0.0, 0.0, 0.0), (1.0, 2.0, 0.0), (0.5, 4.0, 0.0))
    directions = tuple(
        tuple(positions[index + 1][axis] - positions[index][axis] for axis in range(3))
        for index in range(2)
    )
    directions = (*directions, directions[-1])
    matrices = tuple(
        frame_from_y(position, direction)
        for position, direction in zip(positions, directions)
    )
    extents = (
        sum(value * value for value in directions[0]) ** 0.5,
        sum(value * value for value in directions[1]) ** 0.5,
        0.5,
    )

    nodes: list[NodeSpec] = []
    chains: dict[str, tuple[str, str, str]] = {}
    labels = ("upper", "lower", "end")
    for chain_name in ("bind", "fk", "ik"):
        keys = tuple(f"{chain_name}_{label}" for label in labels)
        chains[chain_name] = keys  # type: ignore[assignment]
        for index, (key, label) in enumerate(zip(keys, labels)):
            nodes.append(
                NodeSpec(
                    key=key,
                    name=f"Portable{label.title()}_{chain_name.upper()}_JNT",
                    kind="joint",
                    parent=keys[index - 1] if index else None,
                    world_matrix=matrices[index],
                    extent=extents[index],
                )
            )

    fk_controls = tuple(f"fk_{label}_ctrl" for label in labels)
    for index, (key, label) in enumerate(zip(fk_controls, labels)):
        nodes.append(
            NodeSpec(
                key=key,
                name=f"Portable{label.title()}_FK_CTRL",
                kind="control",
                parent=fk_controls[index - 1] if index else None,
                world_matrix=matrices[index],
            )
        )
    nodes.extend(
        (
            NodeSpec(
                key="ik_target",
                name="PortableLimb_IK_CTRL",
                kind="control",
                world_matrix=matrices[-1],
            ),
            NodeSpec(
                key="pole_vector",
                name="PortableLimb_PV_CTRL",
                kind="control",
                world_matrix=with_translation(matrices[1], 1.0, 2.0, 2.0),
            ),
            NodeSpec(
                key="settings",
                name="PortableLimb_SETTINGS",
                kind="control",
                world_matrix=with_translation(matrices[0], -1.0, 0.0, 0.0),
            ),
        )
    )
    return RigPlan(
        name="三段IKFK跨DCC肢体",
        nodes=tuple(nodes),
        limbs=(
            LimbSpec(
                key="portable_limb",
                bind_chain=chains["bind"],
                fk_chain=chains["fk"],
                ik_chain=chains["ik"],
                fk_controls=fk_controls,  # type: ignore[arg-type]
                ik_target="ik_target",
                pole_vector="pole_vector",
                settings="settings",
            ),
        ),
    )
