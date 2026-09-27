"""Resolve Inbetween limb segments from an already planned character rig."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.body_limb_mechanisms import BodyLimbMechanismRole
from adv_py.core.fit_part import FitPartJointSpec

from .body_character_rig import BodyCharacterRigBuildPlan


_SUPPORTED_EDGES = {
    ("Shoulder", "Elbow"): "arm",
    ("Elbow", "Wrist"): "arm",
    ("Hip", "Knee"): "leg",
    ("Knee", "Ankle"): "leg",
    ("Ankle", "Toes"): "leg",
}


@dataclass(frozen=True, slots=True)
class InbetweenLimbBinding:
    parts: tuple[FitPartJointSpec, ...]
    fk_offset_path: str
    fk_control_path: str
    fk_system_path: str
    start_fk_driver_path: str
    start_fk_constraint_name: str
    downstream_fk_offset_path: str
    start_ik_driver: str
    end_ik_driver: str
    fk_weight_plug: str
    ik_weight_plug: str
    rotate_order: int
    part_control_radius: float


def plan_inbetween_limb_bindings(
    parts: tuple[FitPartJointSpec, ...],
    rig: BodyCharacterRigBuildPlan,
) -> tuple[InbetweenLimbBinding, ...]:
    """Require every Inbetween chain to map to a known Arm/Leg segment."""
    grouped: dict[str, list[FitPartJointSpec]] = {}
    for part in parts:
        if part.kind == "inbetween":
            grouped.setdefault(part.start_body, []).append(part)
    bindings = []
    for start_path, chain in grouped.items():
        chain.sort(key=lambda part: part.index)
        first = chain[0]
        start_name, side = first.start_body_name.rsplit("_", 1)
        end_name, end_side = first.end_body_name.rsplit("_", 1)
        branch = _SUPPORTED_EDGES.get((start_name, end_name))
        if (branch is None or side != end_side
                or any(part.end_body != first.end_body
                       or part.side != first.side
                       or part.count != len(chain)
                       or part.index != index
                       for index, part in enumerate(chain, 1))):
            raise ValueError("Inbetween 段尚不能映射到标准四肢 Rig："
                             + first.start_body_name)
        module = rig.arm if branch == "arm" else rig.leg
        controls = module.fk_controls.controls
        start_controls = [item for item in controls
                          if item.control_name
                          == f"AdvPy_{start_name}FK_{side}"]
        end_controls = [item for item in controls
                        if item.control_name
                        == f"AdvPy_{end_name}FK_{side}"]
        ik = {joint.source_joint: joint.path
              for joint in module.mechanisms.joints
              if joint.role is BodyLimbMechanismRole.IK}
        fk = {joint.source_joint: joint.path
              for joint in module.mechanisms.joints
              if joint.role is BodyLimbMechanismRole.FK}
        blend_sides = [item for item in module.blend.sides
                       if item.side == first.side]
        if (len(start_controls) != 1 or len(end_controls) != 1
                or start_path not in ik or first.end_body not in ik
                or start_path not in fk or first.end_body not in fk
                or len(blend_sides) != 1):
            raise ValueError("Inbetween 四肢机制或控制器规划不完整："
                             + first.start_body_name)
        start_control = start_controls[0]
        if (start_control.driven_joint != fk[start_path]
                or end_controls[0].driven_joint != fk[first.end_body]):
            raise ValueError("Inbetween FK 控制与机制关节映射不一致："
                             + first.start_body_name)
        blend = blend_sides[0]
        bindings.append(InbetweenLimbBinding(
            tuple(chain), start_control.offset_path,
            start_control.control_path,
            module.fk_controls.root_path,
            start_control.driven_joint,
            start_control.constraint_name,
            end_controls[0].offset_path,
            ik[start_path], ik[first.end_body],
            blend.reverse_name + ".outputX",
            module.blend.settings_path + "." + blend.attribute,
            first.rotation_order,
            start_control.radius * 0.2,
        ))
    return tuple(bindings)
