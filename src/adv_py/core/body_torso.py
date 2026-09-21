from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from .body_limb_controls import (
    BodyLimbFkControlPlan, BodyLimbFkControlSpec, BodyLimbFkControlSnapshot,
    audit_body_limb_fk_controls,
)
from .body_skeleton import BodySkeletonSnapshot
from .body_limb_mechanisms import BodyLimbMechanismPlan
from .body_limb_stretch import BodyLimbStretchPlan
from .fit_settings import FitSkeletonValidationError


class BodyTorsoLimbPlan(Protocol):
    @property
    def mechanisms(self) -> BodyLimbMechanismPlan: ...
    @property
    def fk_controls(self) -> BodyLimbFkControlPlan: ...
    @property
    def stretch(self) -> BodyLimbStretchPlan: ...


@dataclass(frozen=True, slots=True)
class BodySpaceAttachment:
    name: str
    source: str
    target: str
    kind: str  # pointConstraint for pelvis translation; parentConstraint for limb frames
    translation_only: bool = False

    @property
    def attributes(self) -> tuple[str, ...]:
        kinds = ("translate", "rotate") if self.kind == "parentConstraint" and not self.translation_only else ("translate",)
        return tuple(f"{kind}{axis}" for kind in kinds for axis in "XYZ")


@dataclass(frozen=True, slots=True)
class BodySpaceAttachmentState:
    name: str
    kind: str
    sources: tuple[str, ...]
    target_inputs: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True, slots=True)
class BodyTorsoPlan:
    controls: BodyLimbFkControlPlan
    pelvis_translation: BodySpaceAttachment
    attachments: tuple[BodySpaceAttachment, ...]

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.controls.root_name,) + tuple(
            name for control in self.controls.controls
            for name in (control.offset_name, control.control_name,
                         control.control_name + "Shape", control.constraint_name)
        ) + tuple(item.name for item in (self.pelvis_translation,) + self.attachments)


@dataclass(frozen=True, slots=True)
class BodyTorsoSnapshot:
    controls: BodyLimbFkControlSnapshot
    attachments: tuple[BodySpaceAttachmentState, ...]


def plan_body_torso(
    body: BodySkeletonSnapshot, arm: BodyTorsoLimbPlan, leg: BodyTorsoLimbPlan,
    *, radius: float = 2.0,
) -> BodyTorsoPlan:
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not isfinite(radius) or radius <= 0:
        raise FitSkeletonValidationError("Torso 控制半径必须是正有限数")
    parents = {
        "Root_M": None, "Spine1_M": "Root_M", "Chest_M": "Spine1_M",
        "Neck_M": "Chest_M", "Head_M": "Neck_M",
        "Scapula_R": "Chest_M", "Scapula_L": "Chest_M",
    }
    joints = {joint.name: joint for joint in body.joints}
    if len(joints) != len(body.joints) or any(name not in joints for name in parents):
        raise FitSkeletonValidationError("Torso 需要唯一的 Root / Spine1 / Chest / Neck / Head / Scapula 骨架")
    if joints["Root_M"].path != body.root:
        raise FitSkeletonValidationError("Torso 根与 Body 根不一致")
    root_name = "AdvPy_TorsoControls"
    root_path = f"|{root_name}"
    controls = []
    by_joint = {}
    for name, parent_name in parents.items():
        joint = joints[name]
        expected_parent = joints[parent_name].path if parent_name else None
        if joint.parent_path != expected_parent:
            raise FitSkeletonValidationError(f"Torso 父链不匹配：{name}")
        parent = by_joint[parent_name].control_path if parent_name else root_path
        offset_name = f"AdvPy_Torso{name}Offset"
        control_name = f"AdvPy_Torso{name}FK"
        spec = BodyLimbFkControlSpec(
            side=joint.side, driven_joint=joint.path,
            offset_path=f"{parent}|{offset_name}", offset_name=offset_name,
            control_path=f"{parent}|{offset_name}|{control_name}", control_name=control_name,
            parent_path=parent, constraint_name=f"AdvPy_Torso{name}Orient",
            world_position=joint.world_position, world_axes=joint.world_axes, radius=float(radius),
        )
        by_joint[name] = spec
        controls.append(spec)
    pelvis = BodySpaceAttachment("AdvPy_TorsoPelvisPoint", controls[0].control_path, body.root, "pointConstraint")
    attachments = []
    for label, module, start, anchor in (("Arm", arm, "Shoulder", "Scapula"), ("Leg", leg, "Hip", "Root")):
        for suffix in ("R", "L"):
            source = joints[f"Scapula_{suffix}"].path if anchor == "Scapula" else body.root
            start_joint = joints.get(f"{start}_{suffix}")
            if start_joint is None or start_joint.parent_path != source:
                raise FitSkeletonValidationError(f"{label} 起点未连接到预期躯干关节")
            roots = tuple(spec for spec in module.mechanisms.joints if spec.source_joint == start_joint.path)
            offsets = tuple(spec for spec in module.fk_controls.controls if spec.driven_joint in {r.path for r in roots})
            stretches = tuple(spec for spec in module.stretch.sides if spec.side == start_joint.side)
            if len(roots) != 2 or len(offsets) != 1 or len(stretches) != 1:
                raise FitSkeletonValidationError(f"{label} 机制链或 FK / stretch 根定义不完整")
            attachments.append(BodySpaceAttachment(
                f"AdvPy_Torso{label}FKSpace_{suffix}", source, offsets[0].offset_path, "parentConstraint",
            ))
            for spec in roots:
                attachments.append(BodySpaceAttachment(
                    f"AdvPy_Torso{label}{spec.role.value.upper()}Origin_{suffix}", source, spec.path, "parentConstraint", True,
                ))
            attachments.append(BodySpaceAttachment(
                f"AdvPy_Torso{label}StretchOrigin_{suffix}", source, stretches[0].start_path, "parentConstraint", True,
            ))
    return BodyTorsoPlan(BodyLimbFkControlPlan(root_path, root_name, tuple(controls)), pelvis, tuple(attachments))


def audit_body_torso(plan: BodyTorsoPlan, snapshot: BodyTorsoSnapshot) -> tuple[str, ...]:
    issues = [item.message for item in audit_body_limb_fk_controls(plan.controls, snapshot.controls, limb_label="Torso")]
    specs = (plan.pelvis_translation,) + plan.attachments
    if tuple(item.name for item in snapshot.attachments) != tuple(spec.name for spec in specs):
        issues.append("Torso 空间连接集合不一致")
    for spec, state in zip(specs, snapshot.attachments):
        if (state.kind != spec.kind or state.sources != (spec.source,)
                or state.target_inputs != tuple((f"{spec.target}.{attr}", spec.name) for attr in spec.attributes)):
            issues.append(f"Torso 空间连接读回失败：{spec.name}")
    return tuple(issues)
