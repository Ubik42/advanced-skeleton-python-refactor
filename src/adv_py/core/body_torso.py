from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from .body_build_options import BodyBuildOptions
from .body_limb_controls import (
    BodyLimbFkControlPlan, BodyLimbFkControlSpec, BodyLimbFkControlSnapshot,
    audit_body_limb_fk_controls,
)
from .body_skeleton import BodySkeletonSnapshot
from .body_spine import BodySpinePlan, with_spine_ik
from .body_limb_mechanisms import BodyLimbMechanismPlan
from .body_limb_stretch import BodyLimbStretchPlan
from .fit_settings import FitSkeletonValidationError
from .body_description import BodyAxialDescription
from .body_head_aim import HeadAimPlan,with_head_aim
from .fit_container import FitUpAxis
from .body_spline import BodySplinePlan,with_spline_ik


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
class BodyLegLockSpace:
    path: str
    matrix_name: str
    decompose_name: str
    root_fkx_path: str
    compensation_source: str | None = None

    @property
    def compensation_input(self) -> str:
        return self.matrix_name + ".matrixIn[0]"

    @property
    def source_input(self) -> str:
        return self.matrix_name + ".matrixIn[1]"


@dataclass(frozen=True, slots=True)
class BodyTorsoPlan:
    controls: BodyLimbFkControlPlan
    pelvis_translation: BodySpaceAttachment
    attachments: tuple[BodySpaceAttachment, ...]
    leg_lock: BodyLegLockSpace
    spine: BodySpinePlan | None = None
    head_aim: HeadAimPlan | None = None
    spline: BodySplinePlan | None = None

    @property
    def root_fkx_path(self) -> str:
        root = next(control for control in self.controls.controls
                    if control.driven_joint == self.pelvis_translation.target)
        if root.source_override_path is None:
            raise FitSkeletonValidationError("Torso Root 缺少 FKX 接收层")
        return root.source_override_path

    @property
    def node_names(self) -> tuple[str, ...]:
        return (self.controls.root_name,) + tuple(
            name for control in self.controls.controls
            for name in (control.offset_name, control.control_name,
                         control.control_name + "Shape", control.constraint_name,
                         *((control.extra_name,) if control.extra_name else ()),
                         *((control.extra_name + "Shape",)
                           if control.extra_curve and control.extra_name else ()),
                         *((control.sub_control_name,
                            control.sub_control_name + "Shape")
                           if control.sub_control_name else ()),
                         *((control.source_override_path.rsplit("|", 1)[-1],)
                           if control.source_override_path is not None else ()))
        ) + (self.leg_lock.path.rsplit("|", 1)[-1],
             self.leg_lock.matrix_name, self.leg_lock.decompose_name) + tuple(item.name for item in (self.pelvis_translation,) + self.attachments) + (self.spine.node_names if self.spine else ()) + (self.head_aim.node_names if self.head_aim else ()) + (self.spline.node_names if self.spline else ())


@dataclass(frozen=True, slots=True)
class BodyTorsoSnapshot:
    controls: BodyLimbFkControlSnapshot
    attachments: tuple[BodySpaceAttachmentState, ...]
    root_fkx_parent_path: str | None = None
    leg_lock_parent_path: str | None = None
    leg_lock_source: str | None = None
    leg_lock_compensation_source: str | None = None
    leg_lock_decompose_source: str | None = None
    leg_lock_channel_sources: tuple[str | None, ...] = ()


def plan_body_torso(
    body: BodySkeletonSnapshot, arm: BodyTorsoLimbPlan, leg: BodyTorsoLimbPlan,
    *, radius: float = 2.0, spine_ik: bool = False, description: BodyAxialDescription | None = None, head_aim: bool = False, up_axis: FitUpAxis = FitUpAxis.Z, build_options: BodyBuildOptions = BodyBuildOptions(),
) -> BodyTorsoPlan:
    if not isinstance(build_options, BodyBuildOptions):
        raise FitSkeletonValidationError("Torso 构建选项类型无效")
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not isfinite(radius) or radius <= 0:
        raise FitSkeletonValidationError("Torso 控制半径必须是正有限数")
    description=BodyAxialDescription() if description is None else description
    if not isinstance(head_aim,bool):raise FitSkeletonValidationError('head_aim 必须是布尔值')
    if not isinstance(description,BodyAxialDescription):raise FitSkeletonValidationError('身体描述类型无效')
    parents=dict(description.parents)
    joints=description.validate(body)
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
        extra_name = f"AdvPy_Torso{name}FKExtra"
        control_name = f"AdvPy_Torso{name}FK"
        offset_path = f"{parent}|{offset_name}"
        extra_path = f"{offset_path}|{extra_name}"
        control_path = f"{extra_path}|{control_name}"
        sub_name = (f"AdvPy_Torso{name}FKSub"
                    if build_options.sub_controllers else None)
        sub_path = (f"{control_path}|{sub_name}"
                    if sub_name is not None else None)
        spec = BodyLimbFkControlSpec(
            side=joint.side, driven_joint=joint.path,
            offset_path=offset_path, offset_name=offset_name,
            control_path=control_path, control_name=control_name,
            parent_path=parent, constraint_name=f"AdvPy_Torso{name}Orient",
            world_position=joint.world_position, world_axes=joint.world_axes, radius=float(radius),
            source_override_path=(
                f"{sub_path or control_path}|AdvPy_RootFKX"
                if name == "Root_M" else None),
            sub_control_path=sub_path,
            sub_control_name=sub_name,
            extra_path=extra_path,
            extra_name=extra_name,
            extra_curve=build_options.extra_controllers,
        )
        by_joint[name] = spec
        controls.append(spec)
    pelvis = BodySpaceAttachment("AdvPy_TorsoPelvisPoint", controls[0].control_path, body.root, "pointConstraint")
    leg_lock = BodyLegLockSpace(
        f"{root_path}|AdvPy_LegLockConstrained",
        "AdvPy_LegLockMM", "AdvPy_LegLockDM",
        controls[0].source_override_path,
    )
    attachments = []
    for label, module, start, anchor in (("Arm", arm, "Shoulder", "Scapula"), ("Leg", leg, "Hip", "Root")):
        for index,suffix in enumerate(("R", "L")):
            source = (joints[description.scapulae[index]].path
                      if anchor == "Scapula" else leg_lock.path)
            start_joint = joints.get(f"{start}_{suffix}")
            expected_parent = (joints[description.scapulae[index]].path
                               if anchor == "Scapula" else body.root)
            if start_joint is None or start_joint.parent_path != expected_parent:
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
    plan = BodyTorsoPlan(BodyLimbFkControlPlan(root_path, root_name, tuple(controls)), pelvis, tuple(attachments), leg_lock)
    if spine_ik:
        plan=with_spine_ik(body,plan) if description==BodyAxialDescription() else with_spline_ik(body,plan,description)
    return with_head_aim(plan,body,description,up_axis) if head_aim else plan


def audit_body_torso(plan: BodyTorsoPlan, snapshot: BodyTorsoSnapshot) -> tuple[str, ...]:
    issues = [item.message for item in audit_body_limb_fk_controls(plan.controls, snapshot.controls, limb_label="Torso")]
    if snapshot.root_fkx_parent_path != plan.root_fkx_path.rsplit("|", 1)[0]:
        issues.append("Root FKX 接收层父链不一致")
    if (snapshot.leg_lock_parent_path != plan.controls.root_path
            or snapshot.leg_lock_source != plan.leg_lock.root_fkx_path + ".worldMatrix[0]"
            or snapshot.leg_lock_compensation_source
            != plan.leg_lock.compensation_source
            or snapshot.leg_lock_decompose_source
            != plan.leg_lock.matrix_name + ".matrixSum"
            or snapshot.leg_lock_channel_sources != tuple(
                plan.leg_lock.decompose_name + ".output" + channel
                for channel in ("Translate", "Rotate", "Scale", "Shear"))):
        issues.append("腿部锁定空间矩阵接线不一致")
    specs = (plan.pelvis_translation,) + plan.attachments
    if tuple(item.name for item in snapshot.attachments) != tuple(spec.name for spec in specs):
        issues.append("Torso 空间连接集合不一致")
    for spec, state in zip(specs, snapshot.attachments):
        if (state.kind != spec.kind or state.sources != (spec.source,)
                or state.target_inputs != tuple((f"{spec.target}.{attr}", spec.name) for attr in spec.attributes)):
            issues.append(f"Torso 空间连接读回失败：{spec.name}")
    return tuple(issues)
