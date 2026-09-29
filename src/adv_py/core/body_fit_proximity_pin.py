"""Plan ADV proximityPin for existing FK controls."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_metadata import FitJointMetadata


@dataclass(frozen=True, slots=True)
class BodyFitProximityPinSpec:
    source_body: str
    fk_control: str
    fk_offset: str
    receiver: str
    mesh: str
    side: str
    input_transform: str
    pin_node: str
    corrected_matrix: str
    blend_matrix: str
    weight_node: str
    delta_matrix: str
    receiver_matrix: str

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.pin_node, self.corrected_matrix,
                self.blend_matrix, self.weight_node,
                self.delta_matrix, self.receiver_matrix)


@dataclass(frozen=True, slots=True)
class BodyFitProximityPinState:
    mesh_transform: str
    offset_world: tuple[float, ...]
    receiver_world: tuple[float, ...]
    receiver_opm_source: str | None
    receiver_opm_value: tuple[float, ...]


def plan_body_fit_proximity_pin(
    metadata: tuple[FitJointMetadata, ...], controls: tuple,
    body_joints: tuple,
) -> tuple[BodyFitProximityPinSpec, ...]:
    bodies = {joint.name.rsplit(":", 1)[-1]: joint.path
              for joint in body_joints}
    if len(bodies) != len(body_joints):
        raise ValueError("Proximity Pin Body 关节短名重复")
    result: list[BodyFitProximityPinSpec] = []
    used: set[str] = set()
    for item in metadata:
        if item.proximity_pin is None:
            continue
        name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        matches = tuple(control for control in controls
                        if name in control.fit_joint_names)
        for control in matches:
            side = control.side.value
            source_body = bodies.get(name + "_" + side)
            if source_body is None:
                raise ValueError("Proximity Pin 来源 Body 关节缺失："
                                 + name + "_" + side)
            terminal = not any(path.startswith(source_body + "|")
                               for path in bodies.values())
            if terminal and not item.control:
                continue
            if control.control_path in used:
                raise ValueError("Proximity Pin 来源 FK 控制重复："
                                 + control.control_path)
            used.add(control.control_path)
            prefix = control.offset_path + "|"
            if not control.control_path.startswith(prefix):
                raise ValueError("Proximity Pin FK 控制层路径无效")
            receiver = prefix + control.control_path[len(prefix):].split(
                "|", 1)[0]
            leaf = control.control_path.rsplit("|", 1)[-1]
            namespace = leaf.rsplit(":", 1)[0] + ":" if ":" in leaf else ""
            stem = namespace + "AdvPy_ProximityPin" + name + "_" + side
            result.append(BodyFitProximityPinSpec(
                source_body, control.control_path, control.offset_path,
                receiver, item.proximity_pin, side,
                stem + "Input", stem, stem + "CorrectedMM",
                stem + "BM", stem + "Weight", stem + "DeltaMM",
                stem + "ReceiverMM"))
        if not matches and any(name + "_" + side in bodies
                               for side in ("M", "R", "L")):
            raise ValueError("Proximity Pin 来源缺少 FK 控制：" + name)
    names = tuple(name for spec in result
                  for name in spec.node_names + (spec.input_transform,))
    if len(names) != len(set(names)):
        raise ValueError("Proximity Pin 生成节点名称重复")
    return tuple(result)
