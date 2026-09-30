from __future__ import annotations

from dataclasses import dataclass, replace
from math import atan2, degrees, isfinite, sqrt

from .body_limb_controls import (
    BodyLimbFkControlSpec, reparent_body_fk_control,
)
from .body_limb_mechanisms import BodyLimbMechanismJointSpec, BodyLimbMechanismRole
from .body_limb_ik import solve_limb_pole_position
from .body_build_options import BodyBuildOptions
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
    solver_joint_list: tuple[str, ...] | None = None
    use_offset_parent_matrix: bool = False
    ik_sub_path: str | None = None
    ik_extra_curve: bool = False

    @property
    def ik_extra_path(self) -> str | None:
        parent = self.ik_control.rsplit("|", 1)[0]
        name = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        return parent if name == "AdvPy_SpineIKExtra" else None

    @property
    def ik_driver(self) -> str:
        return self.ik_sub_path or self.ik_control

    @property
    def pole_extra_path(self) -> str | None:
        parent = self.pole_control.rsplit("|", 1)[0]
        name = parent.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        return parent if name == "AdvPy_SpinePoleExtra" else None

    @property
    def blend_plug(self) -> str:
        return self.ik_control + ".spineIkFk"

    @property
    def roll_plug(self) -> str:
        return self.ik_control + ".waistRoll"

    @property
    def stretch_plug(self) -> str:
        return self.ik_control + ".stretchy"

    @property
    def anti_pop_plug(self) -> str:
        return self.ik_control + ".antiPop"

    @property
    def volume_plug(self) -> str:
        return self.ik_control + ".volume"

    @property
    def pole_lock_plug(self) -> str:
        return self.pole_control + ".lock"

    @property
    def node_names(self) -> tuple[str, ...]:
        return tuple(path.rsplit("|", 1)[-1] for path in (
            self.root_path, self.ik_offset, self.ik_control, self.ik_control + "Shape",
            self.pole_offset, self.pole_control, self.pole_control + "Shape",
            self.waist_output, self.chest_space,
            *((self.ik_extra_path,) if self.ik_extra_path else ()),
            *((self.pole_extra_path,) if self.pole_extra_path else ()),
            *((self.ik_extra_path + "|AdvPy_SpineIKExtraShape",)
              if self.ik_extra_path and self.ik_extra_curve else ()),
            *((self.ik_sub_path, self.ik_sub_path + "Shape")
              if self.ik_sub_path else ()),
        )) + tuple(j.name for j in self.joints) + (
            "AdvPy_SpineIKHandle", "AdvPy_SpineIKEffector", "AdvPy_SpinePoleConstraint",
            "AdvPy_SpineFKRootPoint", "AdvPy_SpineIKRootPoint", "AdvPy_SpineIKChestOrient",
            "AdvPy_SpineReverse", "AdvPy_SpineWaistPoint", "AdvPy_SpineWaistOrient",
            "AdvPy_SpineWaistScale", "AdvPy_SpineChestPoint",
            "AdvPy_SpineChestOrient", "AdvPy_SpineChestScale",
            "AdvPy_SpineStretchStartMM", "AdvPy_SpineStretchTargetMM",
            "AdvPy_SpineStretchDistance", "AdvPy_SpineStretchRatio",
            "AdvPy_SpineStretchClamp", "AdvPy_SpineStretchWeight",
            "AdvPy_SpineStretchBlend", "AdvPy_SpineStretchSegments",
            "AdvPy_SpineVolumeInverse", "AdvPy_SpineVolumePower",
            "AdvPy_SpineVolumeWeight", "AdvPy_SpineVolumeBlend",
            "AdvPy_SpineLength1", "AdvPy_SpineLength2",
            "AdvPy_SpineFatness1", "AdvPy_SpineFatness2",
            "AdvPy_SpinePoleLocalMM", "AdvPy_SpinePoleDistance1",
            "AdvPy_SpinePoleDistance2", "AdvPy_SpinePoleLockWeight",
            "AdvPy_SpinePoleLockBlend1", "AdvPy_SpinePoleLockBlend2",
            "AdvPy_SpineAntiPopNormal", "AdvPy_SpineAntiPopCurve",
            "AdvPy_SpineAntiPopWeight", "AdvPy_SpineAntiPopBlend",
        ) + (("AdvPy_SpineChestSpaceMM", "AdvPy_SpineChestSpacePM")
             if self.use_offset_parent_matrix else
             ("AdvPy_SpineChestSpaceParent",))


def with_spine_ik(body, torso, build_options: BodyBuildOptions = BodyBuildOptions()):
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
    pelvis_parent = (pelvis.source_override_path
                     if pelvis.source_override_joint
                     and not torso.use_offset_parent_matrix
                     else pelvis.control_path)
    base_offset = pelvis_parent + "|AdvPy_SpineBaseFKOffset"
    base_extra_name = "AdvPy_SpineBaseFKExtra"
    base_extra = base_offset + "|" + base_extra_name
    base_control = base_extra + "|AdvPy_SpineBaseFK"
    base_sub_name = ("AdvPy_SpineBaseFKSub"
                     if pelvis.sub_control_path is not None else None)
    base_sub_path = (base_control + "|" + base_sub_name
                     if base_sub_name else None)
    use_fkx = pelvis.source_override_joint
    base_fkx = ((base_sub_path or base_control) + "|AdvPy_SpineBaseFKX"
                if use_fkx else None)
    base = BodyLimbFkControlSpec(
        side=source[0].side, driven_joint=specs[0].path,
        offset_path=base_offset, offset_name="AdvPy_SpineBaseFKOffset",
        control_path=base_control, control_name="AdvPy_SpineBaseFK",
        parent_path=pelvis_parent, constraint_name="AdvPy_SpineBaseFKOrient",
        world_position=source[0].world_position, world_axes=source[0].world_axes, radius=waist.radius,
        extra_path=base_extra, extra_name=base_extra_name,
        extra_curve=pelvis.extra_curve,
        sub_control_path=base_sub_path,
        sub_control_name=base_sub_name,
        source_override_path=base_fkx,
        source_override_joint=use_fkx,
        source_override_segment_scale_compensate=(
            not torso.use_offset_parent_matrix),
        fit_joint_names=(source[0].name.rsplit("_", 1)[0],),
    )
    def child_parent(control: BodyLimbFkControlSpec) -> str:
        return (control.source_override_path
                if control.source_override_joint
                and not torso.use_offset_parent_matrix
                else control.control_path)
    waist = reparent_body_fk_control(
        waist, child_parent(base), driven_joint=specs[1].path)
    chest = reparent_body_fk_control(
        chest, child_parent(waist), driven_joint=specs[2].path)
    space = torso.controls.root_path + "|AdvPy_SpineChestSpace"
    updated_upper = []
    old_to_new = {}
    for control in upper:
        parent = old_to_new.get(control.parent_path, space)
        updated = reparent_body_fk_control(control, parent)
        old_to_new[control.control_path] = updated.control_path
        if control.source_override_path is not None:
            old_to_new[control.source_override_path] = child_parent(updated)
        updated_upper.append(updated)
    ik_offset = torso.controls.root_path + "|AdvPy_SpineIKOffset"
    ik_extra = ik_offset + "|AdvPy_SpineIKExtra"
    ik_control = ik_extra + "|AdvPy_SpineIK"
    pole_offset = torso.controls.root_path + "|AdvPy_SpinePoleOffset"
    pole_extra = pole_offset + "|AdvPy_SpinePoleExtra"
    plan = BodySpinePlan(
        root, tuple(specs), pelvis.control_path,
        (base.control_path, waist.control_path, chest.control_path),
        tuple(j.path for j in source), ik_offset, ik_control,
        pole_offset, pole_extra+"|AdvPy_SpinePole",
        solve_limb_pole_position(*(j.world_position for j in source), source[0].world_axes[1],
                                limb_label="Spine", distance_scale=0.75),
        specs[4].path+"|AdvPy_SpineWaistOutput", space, tuple(lengths),
        use_offset_parent_matrix=torso.use_offset_parent_matrix,
        ik_sub_path=(ik_control + "|AdvPy_SpineIKSub"
                     if build_options.sub_controllers else None),
        ik_extra_curve=build_options.extra_controllers,
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
