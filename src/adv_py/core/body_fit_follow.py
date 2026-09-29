"""Resolve ADV Fit follow targets for existing FK controller paths."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata


@dataclass(frozen=True, slots=True)
class BodyFitFollowSpec:
    source_joint: str
    fk_control: str
    fk_offset: str
    receiver: str
    primary_target: str
    opposite_target: str | None
    world_target: bool
    primary_matrix: str
    opposite_matrix: str | None
    blend_matrix: str
    delta_matrix: str
    receiver_matrix: str
    primary_weight: str
    opposite_weight: str | None
    world_weight: str | None

    @property
    def node_names(self) -> tuple[str, ...]:
        return tuple(value for value in (
            self.primary_matrix, self.opposite_matrix,
            self.blend_matrix, self.delta_matrix,
            self.receiver_matrix, self.primary_weight,
            self.opposite_weight, self.world_weight) if value is not None)


@dataclass(frozen=True, slots=True)
class BodyFitFollowSourceState:
    receiver_opm_source: str | None
    receiver_opm_value: tuple[float, ...]
    offset_world: tuple[float, ...]
    receiver_world: tuple[float, ...]
    primary_world: tuple[float, ...]
    opposite_world: tuple[float, ...] | None


def plan_body_fit_follow(
    metadata: tuple[FitJointMetadata, ...],
    controls: tuple,
    body_joints: tuple,
) -> tuple[BodyFitFollowSpec, ...]:
    by_name = {joint.name.rsplit(":", 1)[-1]: joint.path
               for joint in body_joints}
    if len(by_name) != len(body_joints):
        raise ValueError("Fit Follow Body 关节短名重复")
    result = []
    used = set()
    for item in metadata:
        if item.follow is None:
            continue
        source_name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        for control in controls:
            if source_name not in control.fit_joint_names:
                continue
            side = control.side.value
            center = by_name.get(item.follow + "_M")
            right = by_name.get(item.follow + "_R")
            left = by_name.get(item.follow + "_L")
            primary = (center if side == "M" and center is not None
                       else (right if side == "M" else
                             by_name.get(item.follow + "_" + side)))
            primary = primary or center
            if primary is None:
                raise ValueError("Fit Follow 目标 Body 关节缺失："
                                 + item.follow + "_" + side)
            opposite = None
            if item.follow_left_right:
                opposite = left if side in ("M", "R") else right
                if opposite is None:
                    raise ValueError("Fit Follow 左右切换缺少对侧目标："
                                     + item.follow)
            if (primary == control.driven_joint
                    or primary.startswith(control.driven_joint + "|")
                    or (opposite is not None and (
                        opposite == control.driven_joint
                        or opposite.startswith(control.driven_joint + "|")))):
                raise ValueError("Fit Follow 目标依赖自身 FK：" + source_name)
            if control.control_path in used:
                raise ValueError("Fit Follow 来源 FK 控制重复："
                                 + control.control_path)
            used.add(control.control_path)
            prefix = control.offset_path + "|"
            if not control.control_path.startswith(prefix):
                raise ValueError("Fit Follow 控制器不在 FK Offset 下")
            receiver = prefix + control.control_path[len(prefix):].split("|", 1)[0]
            leaf = control.control_path.rsplit("|", 1)[-1]
            ns = leaf.split(":", 1)[0] + ":" if ":" in leaf else ""
            stem = ns + "AdvPy_Follow" + source_name + "_" + side
            result.append(BodyFitFollowSpec(
                item.joint, control.control_path, control.offset_path,
                receiver, primary, opposite, item.follow_world,
                stem + "PrimaryMM",
                stem + "OppositeMM" if opposite is not None else None,
                stem + "BM", stem + "DeltaMM", stem + "ReceiverMM",
                stem + "Weight",
                stem + "OppositeWeight" if opposite is not None else None,
                stem + "WorldWeight" if item.follow_world else None))
    names = tuple(name for spec in result for name in spec.node_names)
    if len(names) != len(set(names)):
        raise ValueError("Fit Follow 节点名称重复")
    return tuple(result)
