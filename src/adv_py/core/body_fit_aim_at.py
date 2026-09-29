"""Resolve ADV Fit aimAt targets against built FK controls."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata


@dataclass(frozen=True, slots=True)
class BodyFitAimAtSpec:
    source_body: str
    target_body: str
    fk_control: str
    fk_offset: str
    receiver: str
    target_control: str
    aim_axis: str
    up_axis: str
    up_object: str
    mirror_sign: int
    aim_matrix: str
    corrected_matrix: str
    blend_matrix: str
    weight_node: str
    delta_matrix: str
    rotation_pick: str
    receiver_matrix: str

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.aim_matrix, self.corrected_matrix,
                self.blend_matrix, self.weight_node,
                self.delta_matrix, self.rotation_pick,
                self.receiver_matrix)


@dataclass(frozen=True, slots=True)
class BodyFitAimAtState:
    offset_world: tuple[float, ...]
    receiver_world: tuple[float, ...]
    target_world: tuple[float, ...]
    receiver_opm_source: str | None
    receiver_opm_value: tuple[float, ...]


def plan_body_fit_aim_at(
    metadata: tuple[FitJointMetadata, ...],
    controls: tuple, body_joints: tuple,
) -> tuple[BodyFitAimAtSpec, ...]:
    by_name = {joint.name.rsplit(":", 1)[-1]: joint.path
               for joint in body_joints}
    if len(by_name) != len(body_joints):
        raise ValueError("Fit AimAt Body 关节短名重复")
    body_paths = set(by_name.values())
    result = []
    used = set()
    for item in metadata:
        if item.aim_at is None:
            continue
        source_name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        matches = tuple(control for control in controls
                        if source_name in control.fit_joint_names)
        for control in matches:
            side = control.side.value
            source_body = by_name.get(source_name + "_" + side)
            if source_body is None:
                raise ValueError("Fit AimAt 来源 Body 关节缺失："
                                 + source_name + "_" + side)
            # ADV skips terminal Fit joints without a child.
            if not any(path.startswith(source_body + "|")
                       for path in body_paths):
                continue
            target_body = (by_name.get(item.aim_at + "_" + side)
                           or by_name.get(item.aim_at + "_M")
                           or (by_name.get(item.aim_at + "_R")
                               if side == "M" else None))
            if target_body is None:
                raise ValueError("Fit AimAt 目标 Body 关节缺失："
                                 + item.aim_at + "_" + side)
            if (target_body == source_body
                    or target_body.startswith(source_body + "|")):
                raise ValueError("Fit AimAt 目标依赖自身 FK："
                                 + target_body)
            target_side = target_body.rsplit("_", 1)[-1]
            target_controls = tuple(candidate for candidate in controls
                if item.aim_at in candidate.fit_joint_names
                and candidate.side.value == target_side)
            direct = tuple(candidate for candidate in target_controls
                           if candidate.driven_joint == target_body)
            target_controls = direct or target_controls
            if len(target_controls) != 1:
                raise ValueError("Fit AimAt 缺少唯一目标 FK 控制："
                                 + item.aim_at + "_" + target_side)
            if control.control_path in used:
                raise ValueError("Fit AimAt 来源 FK 控制重复："
                                 + control.control_path)
            used.add(control.control_path)
            prefix = control.offset_path + "|"
            if not control.control_path.startswith(prefix):
                raise ValueError("Fit AimAt 控制器不在 FK Offset 下")
            receiver = prefix + control.control_path[len(prefix):].split("|", 1)[0]
            leaf = control.control_path.rsplit("|", 1)[-1]
            namespace = leaf.rsplit(":", 1)[0] + ":" if ":" in leaf else ""
            stem = namespace + "AdvPy_AimAt" + source_name + "_" + side
            result.append(BodyFitAimAtSpec(
                source_body, target_body, control.control_path,
                control.offset_path, receiver,
                target_controls[0].control_path,
                item.aim_axis, item.aim_up_axis,
                item.aim_up_object, -1 if side == "L" else 1,
                stem + "AM", stem + "CorrectedMM", stem + "BM",
                stem + "Weight", stem + "DeltaMM",
                stem + "RotationPM", stem + "ReceiverMM"))
        if not matches and any(source_name + "_" + side in by_name
                               for side in ("M", "R", "L")):
            raise ValueError("Fit AimAt 来源缺少 FK 控制：" + source_name)
    names = tuple(name for spec in result for name in spec.node_names)
    if len(names) != len(set(names)):
        raise ValueError("Fit AimAt 生成节点名称重复")
    return tuple(result)
