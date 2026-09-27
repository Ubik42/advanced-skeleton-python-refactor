"""Resolve supported Inbetween segments from an already planned character rig."""
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
_SPINE_EDGES = {("Root_M", "Spine1_M"),
                ("Spine1_M", "Chest_M")}


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


@dataclass(frozen=True, slots=True)
class InbetweenFkBinding:
    parts: tuple[FitPartJointSpec, ...]
    fk_offset_path: str
    fk_control_path: str
    fk_system_path: str
    start_fk_driver_path: str
    start_fk_constraint_name: str
    downstream_fk_offset_path: str
    rotate_order: int
    part_control_radius: float


def plan_inbetween_limb_bindings(
    parts: tuple[FitPartJointSpec, ...],
    rig: BodyCharacterRigBuildPlan,
) -> tuple[InbetweenLimbBinding | InbetweenFkBinding, ...]:
    """Map Inbetween chains to the actual FK/IK mechanism and control paths."""
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
        spine_edge = (first.start_body_name, first.end_body_name) in _SPINE_EDGES
        neck_edge = (first.start_body_name,
                     first.end_body_name) == ("Neck_M", "Head_M")
        if ((branch is None and not spine_edge and not neck_edge)
                or side != end_side
                or any(part.start_body != first.start_body
                       or part.end_body != first.end_body
                       or part.side != first.side
                       or part.count != len(chain)
                       or part.index != index
                       for index, part in enumerate(chain, 1))):
            raise ValueError("Inbetween 段尚不能映射到标准 Rig："
                             + first.start_body_name)
        if neck_edge:
            if rig.torso is None or rig.torso.torso.head_aim is not None:
                raise ValueError("颈部 Inbetween 需要标准 Torso FK 控制")
            torso = rig.torso.torso
            controls = torso.controls.controls
            start_controls = [item for item in controls
                              if item.driven_joint == start_path]
            end_controls = [item for item in controls
                            if item.driven_joint == first.end_body]
            if len(start_controls) != 1 or len(end_controls) != 1:
                raise ValueError("颈部 Inbetween 控制映射不完整")
            start_control = start_controls[0]
            bindings.append(InbetweenFkBinding(
                tuple(chain), start_control.offset_path,
                start_control.control_path, torso.controls.root_path,
                start_path, start_control.constraint_name,
                end_controls[0].offset_path,
                first.rotation_order, start_control.radius * 0.2,
            ))
            continue
        if spine_edge:
            if rig.torso is None or rig.torso.torso.spine is None:
                raise ValueError("轴向 Inbetween 需要 Spine FK／IK 机制")
            torso = rig.torso.torso
            spine = torso.spine
            controls = torso.controls.controls
            control_by_name = {item.control_name: item for item in controls}
            if start_name == "Root":
                start_control = control_by_name.get("AdvPy_SpineBaseFK")
                end_control = control_by_name.get("AdvPy_TorsoSpine1FK")
                fk_index, ik_index = 0, 3
            else:
                start_control = control_by_name.get("AdvPy_TorsoSpine1FK")
                end_control = control_by_name.get("AdvPy_TorsoChestFK")
                fk_index, ik_index = 1, 4
            if (start_control is None or end_control is None
                    or spine.body_joints[fk_index] != start_path
                    or spine.body_joints[fk_index + 1] != first.end_body
                    or start_control.driven_joint != spine.joints[fk_index].path
                    or end_control.driven_joint != spine.joints[fk_index + 1].path):
                raise ValueError("轴向 Inbetween 控制与 Spine 机制映射不一致："
                                 + first.start_body_name)
            bindings.append(InbetweenLimbBinding(
                tuple(chain), start_control.offset_path,
                start_control.control_path, torso.controls.root_path,
                start_control.driven_joint,
                start_control.constraint_name, end_control.offset_path,
                spine.joints[ik_index].path,
                spine.joints[ik_index + 1].path,
                "AdvPy_SpineReverse.outputX", spine.blend_plug,
                first.rotation_order, start_control.radius * 0.2,
            ))
            continue
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
