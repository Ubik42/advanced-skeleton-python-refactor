from __future__ import annotations

from dataclasses import dataclass, replace
from math import atan2, degrees, isfinite, sqrt

from .body_limb_controls import BodyLimbFkControlSpec
from .body_limb_mechanisms import BodyLimbMechanismJointSpec, BodyLimbMechanismRole
from .body_limb_ik import solve_limb_pole_position
from .fit_settings import FitSkeletonValidationError

SPINE_MATCH_TOLERANCE = 1e-4
SpineWorldPose = tuple[tuple[str, tuple[float, ...]], ...]


def spine_pose_error(before: SpineWorldPose, after: SpineWorldPose) -> float:
    if (not before or tuple(path for path, _ in before) != tuple(path for path, _ in after)
            or len({path for path, _ in before}) != len(before)
            or any(len(matrix) != 16 or not all(isfinite(v) for v in matrix) for _, matrix in before + after)):
        raise FitSkeletonValidationError("Spine 世界姿态快照不完整或数值无效")
    return max(abs(a-b) for (_, left), (_, right) in zip(before, after) for a, b in zip(left, right))


@dataclass(frozen=True, slots=True)
class BodySpinePlan:
    root_path: str
    joints: tuple[BodyLimbMechanismJointSpec, ...]
    pelvis_control: str
    fk_controls: tuple[str, str, str]
    body_joints: tuple[str, str, str]
    ik_offset: str
    ik_control: str
    pole_offset: str
    pole_control: str
    pole_position: tuple[float, float, float]
    waist_output: str
    chest_space: str
    lengths: tuple[float, float]

    @property
    def blend_plug(self) -> str:
        return self.ik_control + ".spineIkFk"

    @property
    def roll_plug(self) -> str:
        return self.ik_control + ".waistRoll"

    @property
    def node_names(self) -> tuple[str, ...]:
        return tuple(path.rsplit("|", 1)[-1] for path in (
            self.root_path, self.ik_offset, self.ik_control, self.ik_control + "Shape",
            self.pole_offset, self.pole_control, self.pole_control + "Shape",
            self.waist_output, self.chest_space,
        )) + tuple(j.name for j in self.joints) + (
            "AdvPy_SpineIKHandle", "AdvPy_SpineIKEffector", "AdvPy_SpinePoleConstraint",
            "AdvPy_SpineFKRootPoint", "AdvPy_SpineIKRootPoint", "AdvPy_SpineIKChestOrient",
            "AdvPy_SpineReverse", "AdvPy_SpineWaistPoint", "AdvPy_SpineWaistOrient",
            "AdvPy_SpineChestPoint", "AdvPy_SpineChestOrient", "AdvPy_SpineChestSpaceParent",
        )


def with_spine_ik(body, torso):
    """Extend the fixed torso topology with a separate two-segment spine mechanism."""
    states = {j.name: j for j in body.joints}
    source = tuple(states[name] for name in ("Root_M", "Spine1_M", "Chest_M"))
    # The pelvis frame also serves the legs. Give the independent spine base its
    # own +X aim without changing the Body root or relying on its orientation.
    direction = tuple(b-a for a, b in zip(source[0].world_position, source[1].world_position))
    size = sqrt(sum(v*v for v in direction))
    if not isfinite(size) or size < 1e-5:
        raise FitSkeletonValidationError("Spine 基部骨段长度无效")
    x = tuple(v / size for v in direction)
    candidates = source[1].world_axes
    guide = min(candidates, key=lambda axis: abs(sum(a*b for a, b in zip(axis, x))))
    projection = sum(a*b for a, b in zip(guide, x))
    y = tuple(a-projection*b for a, b in zip(guide, x))
    norm = sqrt(sum(v*v for v in y))
    y = tuple(v / norm for v in y)
    z = (x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0])
    source = (replace(source[0], world_axes=(x, y, z)), *source[1:])
    lengths = []
    for parent, child in zip(source, source[1:]):
        delta = tuple(b-a for a, b in zip(parent.world_position, child.world_position))
        length = sqrt(sum(v*v for v in delta))
        projection = sum(a*b for a, b in zip(delta, parent.world_axes[0]))
        if not isfinite(length) or length < 1e-5 or abs(length-projection) > 1e-4:
            raise FitSkeletonValidationError("Spine IK 要求两个非零骨段沿父关节本地 +X")
        lengths.append(length)
    root = torso.controls.root_path + "|AdvPy_SpineMechanisms"
    specs = []
    for role in (BodyLimbMechanismRole.FK, BodyLimbMechanismRole.IK):
        parent = root
        for label, joint in zip(("Root", "Waist", "Chest"), source):
            name = f"AdvPy_Spine{role.value.upper()}{label}"
            specs.append(BodyLimbMechanismJointSpec(
                role, joint.side, joint.path, parent+"|"+name, name, parent,
                joint.world_position, joint.world_axes,
            ))
            parent = specs[-1].path
    pelvis, waist, chest, *upper = torso.controls.controls
    base_offset = pelvis.control_path + "|AdvPy_SpineBaseFKOffset"
    base = BodyLimbFkControlSpec(
        side=source[0].side, driven_joint=specs[0].path,
        offset_path=base_offset, offset_name="AdvPy_SpineBaseFKOffset",
        control_path=base_offset+"|AdvPy_SpineBaseFK", control_name="AdvPy_SpineBaseFK",
        parent_path=pelvis.control_path, constraint_name="AdvPy_SpineBaseFKOrient",
        world_position=source[0].world_position, world_axes=source[0].world_axes, radius=waist.radius,
    )
    waist_offset = base.control_path + "|" + waist.offset_name
    waist = replace(waist, parent_path=base.control_path, offset_path=waist_offset,
                    control_path=waist_offset+"|"+waist.control_name, driven_joint=specs[1].path)
    chest_offset = waist.control_path + "|" + chest.offset_name
    chest = replace(chest, parent_path=waist.control_path, offset_path=chest_offset,
                    control_path=chest_offset+"|"+chest.control_name, driven_joint=specs[2].path)
    space = torso.controls.root_path + "|AdvPy_SpineChestSpace"
    updated_upper = []
    old_to_new = {}
    for control in upper:
        parent = old_to_new.get(control.parent_path, space)
        offset = parent + "|" + control.offset_name
        updated = replace(control, parent_path=parent, offset_path=offset,
                          control_path=offset+"|"+control.control_name)
        old_to_new[control.control_path] = updated.control_path
        updated_upper.append(updated)
    ik_offset = torso.controls.root_path + "|AdvPy_SpineIKOffset"
    pole_offset = torso.controls.root_path + "|AdvPy_SpinePoleOffset"
    plan = BodySpinePlan(
        root, tuple(specs), pelvis.control_path,
        (base.control_path, waist.control_path, chest.control_path),
        tuple(j.path for j in source), ik_offset, ik_offset+"|AdvPy_SpineIK",
        pole_offset, pole_offset+"|AdvPy_SpinePole",
        solve_limb_pole_position(*(j.world_position for j in source), source[0].world_axes[1],
                                limb_label="Spine", distance_scale=0.75),
        specs[4].path+"|AdvPy_SpineWaistOutput", space, tuple(lengths),
    )
    return replace(torso, controls=replace(torso.controls, controls=(pelvis, base, waist, chest, *updated_upper)), spine=plan)


def spine_roll_degrees(wanted_axes, solved_axes, tolerance=1e-4):
    """The solver controls swing; the waist control restores independent local-X roll."""
    if max(abs(a-b) for a, b in zip(wanted_axes[0], solved_axes[0])) > tolerance:
        raise FitSkeletonValidationError(f"Spine IK waist aim mismatch: {wanted_axes[0]!r} / {solved_axes[0]!r}")
    y = sum(a*b for a, b in zip(wanted_axes[1], solved_axes[1]))
    z = sum(a*b for a, b in zip(wanted_axes[1], solved_axes[2]))
    return degrees(atan2(z, y))


def spine_ik_goal_position(start, middle, end):
    """Bias a fully extended goal outwards so RP evaluates its exact reach limit."""
    length = sum(sqrt(sum((a-b)**2 for a, b in zip(left, right))) for left, right in ((start, middle), (middle, end)))
    delta = tuple(b-a for a, b in zip(start, end))
    reach = sqrt(sum(v*v for v in delta))
    if reach > 1e-5 and abs(length-reach) <= max(1.0, length)*1e-8:
        return tuple(p + d/reach * max(1.0, length)*1e-5 for p, d in zip(end, delta))
    return end
