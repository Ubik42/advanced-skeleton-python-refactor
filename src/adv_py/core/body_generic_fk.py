"""FK controls for Fit branches outside the named torso/limb/hand chains."""
from __future__ import annotations

from dataclasses import dataclass

from .body_controller_appearance import body_fk_curve_radius
from .body_limb_controls import BodyLimbFkControlSpec
from .body_skeleton import BodyJointSpec, BodySkeletonSnapshot
from .fit_metadata import FitJointMetadata


@dataclass(frozen=True, slots=True)
class BodyGenericFkPlan:
    root_path: str
    controls: tuple[BodyLimbFkControlSpec, ...]
    hidden_controls: tuple[str, ...]


def plan_body_generic_fk(
    body: BodySkeletonSnapshot,
    specs: tuple[BodyJointSpec, ...],
    metadata: tuple[FitJointMetadata, ...],
    existing: tuple[BodyLimbFkControlSpec, ...],
    *, sub_controllers: bool, extra_controllers: bool,
    radius: float = 1.5,
) -> BodyGenericFkPlan:
    root_path = "|Group|MotionSystem|FKSystem|AdvPy_GenericFKControls"
    state_by_name = {state.name: state for state in body.joints}
    metadata_by_source = {item.joint: item for item in metadata}
    spec_by_path = {spec.path: spec for spec in specs}
    child_paths = {spec.parent_path for spec in specs}
    first_child: dict[str, str] = {}
    for spec in specs:
        if spec.parent_path is not None:
            first_child.setdefault(spec.parent_path, spec.name)
    control_by_name = {
        name + "_" + control.side.value: control.control_path
        for control in existing for name in control.fit_joint_names
    }
    controls: list[BodyLimbFkControlSpec] = []
    hidden: list[str] = []
    for spec in sorted(specs, key=lambda item: (item.path.count("|"),
                                                item.path)):
        item = metadata_by_source[spec.source_joint]
        source_name = (spec.source_joint.rsplit("|", 1)[-1]
                       .rsplit(":", 1)[-1]
                       .removesuffix("_NonSymmetry"))
        if (spec.name in control_by_name
                or source_name + "_" + spec.side.value in control_by_name):
            continue
        if spec.path not in child_paths and not item.control:
            continue
        state = state_by_name.get(spec.name)
        if state is None:
            raise ValueError("通用 FK 缺少 Body 关节：" + spec.name)
        parent_control = root_path
        parent_spec = spec.parent_path
        while parent_spec is not None:
            parent_name = parent_spec.rsplit("|", 1)[-1]
            if parent_name in control_by_name:
                parent_control = control_by_name[parent_name]
                break
            parent_spec = (spec_by_path[parent_spec].parent_path
                           if parent_spec in spec_by_path else None)
        stem = spec.name
        offset_name = "AdvPy_" + stem + "FKOffset"
        extra_name = "AdvPy_" + stem + "FKExtra"
        control_name = "AdvPy_" + stem + "FK"
        offset_path = parent_control + "|" + offset_name
        aim_name = ("AdvPy_" + stem + "FKGuideAim"
                    if item.curve_guide is not None else None)
        aim_path = (offset_path + "|" + aim_name
                    if aim_name is not None else None)
        extra_path = (aim_path or offset_path) + "|" + extra_name
        control_path = extra_path + "|" + control_name
        sub_name = ("AdvPy_" + stem + "FKSub"
                    if sub_controllers else None)
        sub_path = (control_path + "|" + sub_name
                    if sub_name is not None else None)
        control = BodyLimbFkControlSpec(
            side=spec.side,
            driven_joint=state.path,
            offset_path=offset_path,
            offset_name=offset_name,
            control_path=control_path,
            control_name=control_name,
            parent_path=parent_control,
            constraint_name="AdvPy_" + stem + "FKOrient",
            world_position=state.world_position,
            world_axes=state.world_axes,
            radius=body_fk_curve_radius(
                body, state, radius,
                preferred_child=state_by_name.get(first_child.get(spec.path))),
            rotate_order=state.rotation_order,
            sub_control_path=sub_path,
            sub_control_name=sub_name,
            source_override_path=(sub_path or control_path)
                                 + "|AdvPy_" + stem + "FKX",
            extra_path=extra_path,
            extra_name=extra_name,
            extra_curve=extra_controllers,
            fit_joint_names=(source_name,),
            aim_path=aim_path,
            aim_name=aim_name,
        )
        controls.append(control)
        control_by_name[spec.name] = control_path
        if item.no_control:
            hidden.append(control_path)
    return BodyGenericFkPlan(root_path, tuple(controls), tuple(hidden))
