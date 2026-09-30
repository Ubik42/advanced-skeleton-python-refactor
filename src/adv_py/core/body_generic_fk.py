"""FK controls for Fit branches outside the named torso/limb/hand chains."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .body_controller_appearance import body_fk_curve_radius
from .body_limb_controls import BodyLimbFkControlSpec
from .body_hand_fit import (advanced_skeleton_hand_source_joint_names,
                            body_hand_source_joint_names)
from .body_skeleton import (
    BodyJointSpec, BodySkeletonSnapshot, plan_body_non_deform_markers,
)
from .fit_metadata import FitJointMetadata
from .fit_scale_compensation import fit_segment_scale_compensate


@dataclass(frozen=True, slots=True)
class BodyGenericFkFollowerSpec:
    path: str
    name: str
    source_body_joint: str
    use_offset_parent_matrix: bool
    inherit_scale: bool
    use_parent_constraint: bool = False
    scale_source_body_joint: str | None = None

    @property
    def driver_name(self) -> str:
        return self.name + ("MM" if self.use_offset_parent_matrix
                            else "Constraint")

    @property
    def pick_name(self) -> str:
        return self.name + "Pick"

    @property
    def point_name(self) -> str:
        return self.name + "Point"

    @property
    def orient_name(self) -> str:
        return self.name + "Orient"


@dataclass(frozen=True, slots=True)
class BodyGenericFkEndpointSpec:
    path: str
    name: str
    parent_path: str
    driven_joint: str
    world_position: tuple[float, float, float]
    world_axes: tuple[tuple[float, float, float], ...]
    rotate_order: int
    follow_fk_matrix: str | None = None
    follow_ik_matrix: str | None = None
    follow_blend_plug: str | None = None

    def __post_init__(self) -> None:
        if ((self.follow_ik_matrix is None)
                != (self.follow_blend_plug is None)
                or (self.follow_ik_matrix is not None
                    and self.follow_fk_matrix is None)):
            raise ValueError("Bendy 末端 FK／IK 矩阵来源不完整：" + self.name)

    @property
    def matrix_name(self) -> str:
        return self.name + "MM"

    @property
    def blend_name(self) -> str:
        return self.name + "Blend"


@dataclass(frozen=True, slots=True)
class BodyGenericFkPlan:
    root_path: str
    controls: tuple[BodyLimbFkControlSpec, ...]
    hidden_controls: tuple[str, ...]
    followers: tuple[BodyGenericFkFollowerSpec, ...] = ()
    finger_visibility_plug: str | None = None
    endpoints: tuple[BodyGenericFkEndpointSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class GenericFkFeaturePolicy:
    """Retain the generated graph of a saved character during rebuilding.

    None enables the current behavior for fresh characters. A set limits a
    feature to controls already carrying that feature in the saved rig.
    """

    scale_controls: frozenset[str] | None = None
    compensated_controls: frozenset[str] | None = None
    global_controls: frozenset[str] | None = None
    aim_sources: frozenset[str] | None = None
    follower_sources: frozenset[str] | None = None
    independent_controls: frozenset[str] | None = None
    twist_rewired_sources: frozenset[str] | None = None
    bendy_scale_controls: frozenset[str] | None = None
    standard_fkx_joint_names: frozenset[str] | None = None
    hand_fkx_joint_names: frozenset[str] | None = None
    standard_fk_independent_controls: frozenset[str] | None = None
    bendy_aim_follow_controls: frozenset[str] | None = None
    bendy_start_control_sources: frozenset[str] | None = None
    bendy_child_control_sources: frozenset[str] | None = None
    bendy_untwist_controls: frozenset[str] | None = None
    bendy_end_matrix_controls: frozenset[str] | None = None
    bendy_oriented_controls: frozenset[str] | None = None
    bendy_negative_right_axes: frozenset[str] | None = None
    bendy_micro_matrix_controls: frozenset[str] | None = None
    bendy_base_twist_controls: frozenset[str] | None = None
    bendy_micro_scale_controls: frozenset[str] | None = None
    bendy_control_counts: tuple[tuple[str, int], ...] | None = None
    bendy_yz_scale_controls: frozenset[str] | None = None
    bendy_up_twist_controls: frozenset[str] | None = None
    bendy_blended_up_controls: frozenset[str] | None = None
    bendy_legacy_simple_controls: frozenset[str] | None = None
    bendy_legacy_twist_outputs: frozenset[str] | None = None
    bendy_master_circular_controls: frozenset[str] | None = None
    bendy_legacy_start_icon_controls: frozenset[str] | None = None
    bendy_parented_end_controls: frozenset[str] | None = None
    bendy_legacy_circular_controls: frozenset[str] | None = None
    bendy_legacy_full_span_controls: frozenset[str] | None = None
    bendy_scaled_guide_controls: frozenset[str] | None = None
    bendy_additive_micro_scale_controls: frozenset[str] | None = None
    bendy_opm_offset_scale_controls: frozenset[str] | None = None
    bendy_secondary_matrix_controls: frozenset[str] | None = None
    bendy_main_influence_controls: frozenset[str] | None = None
    fkx_joint_controls: frozenset[str] | None = None


def plan_body_generic_fk(
    body: BodySkeletonSnapshot,
    specs: tuple[BodyJointSpec, ...],
    metadata: tuple[FitJointMetadata, ...],
    existing: tuple[BodyLimbFkControlSpec, ...],
    *, sub_controllers: bool, extra_controllers: bool,
    radius: float = 1.5,
    aim_sources: frozenset[str] | None = None,
    inbetween_start_paths: frozenset[str] = frozenset(),
    use_offset_parent_matrix: bool = False,
    remapped_body_paths: Mapping[str, str] | None = None,
    root_follow_transform: str | None = None,
    follower_sources: frozenset[str] | None = None,
    finger_visibility_plug: str | None = None,
    bendy_end_paths: frozenset[str] = frozenset(),
    bendy_parent_sources: Mapping[
        str, tuple[str, str | None, str | None]] | None = None,
    fkx_joint_controls: frozenset[str] | None = None,
) -> BodyGenericFkPlan:
    root_path = "|Group|MotionSystem|FKSystem|AdvPy_GenericFKControls"
    state_by_name = {state.name.rsplit(":", 1)[-1]: state
                     for state in body.joints}
    metadata_by_source = {item.joint: item for item in metadata}
    spec_by_path = {spec.path: spec for spec in specs}
    removable_body_paths = frozenset(plan_body_non_deform_markers(body))
    child_paths = {spec.parent_path for spec in specs}
    first_child: dict[str, str] = {}
    for spec in specs:
        if spec.parent_path is not None:
            first_child.setdefault(spec.parent_path, spec.name)
    control_by_name = {
        name + "_" + control.side.value: control.control_path
        for control in existing for name in control.fit_joint_names
    }
    standard_names = frozenset(control_by_name)
    controls: list[BodyLimbFkControlSpec] = []
    hidden: list[str] = []
    followers: dict[str, BodyGenericFkFollowerSpec] = {}
    endpoints: list[BodyGenericFkEndpointSpec] = []
    finger_names = frozenset(body_hand_source_joint_names()) | frozenset(
        advanced_skeleton_hand_source_joint_names())
    for spec in sorted(specs, key=lambda item: (item.path.count("|"),
                                                item.path)):
        final_path = (remapped_body_paths or {}).get(spec.path, spec.path)
        if final_path in removable_body_paths:
            continue
        item = metadata_by_source[spec.source_joint]
        source_leaf = (spec.source_joint.rsplit("|", 1)[-1]
                       .rsplit(":", 1)[-1])
        source_name = source_leaf.removesuffix("_NonSymmetry")
        if (spec.name in control_by_name
                or source_name + "_" + spec.side.value in control_by_name):
            continue
        needs_endpoint = (final_path in bendy_end_paths
                          and spec.path not in child_paths
                          and not item.control
                          and not (use_offset_parent_matrix
                                   and item.tweaker_control))
        if (spec.path not in child_paths
                and not item.control
                and not (use_offset_parent_matrix
                         and item.tweaker_control)
                and not needs_endpoint):
            continue
        state = state_by_name.get(spec.name)
        if state is None or state.path != final_path:
            raise ValueError("通用 FK 缺少最终 Body 关节：" + spec.name)
        parent_control = root_path
        parent_spec = spec.parent_path
        standard_parent = False
        while parent_spec is not None:
            parent_name = (parent_spec.rsplit("|", 1)[-1]
                           .rsplit(":", 1)[-1])
            if parent_name in control_by_name:
                parent_control = control_by_name[parent_name]
                standard_parent = parent_name in standard_names
                break
            parent_spec = (spec_by_path[parent_spec].parent_path
                           if parent_spec in spec_by_path else None)
        final_parent = ((remapped_body_paths or {}).get(
            spec.parent_path, spec.parent_path)
            if spec.parent_path is not None else None)
        child_of_part = (final_parent is not None
                         and final_path.rsplit("|", 1)[0] != final_parent)
        if (not needs_endpoint and spec.parent_path is not None
                and (standard_parent or child_of_part
                     or item.child_of_part not in (None, 0))):
            source_parent = spec.parent_path
            while (source_parent in removable_body_paths
                   and source_parent in spec_by_path):
                source_parent = spec_by_path[source_parent].parent_path
            if source_parent is None:
                raise ValueError("通用 FK 跟随分支缺少保留的 Body 父级："
                                 + spec.name)
            body_joint = ((remapped_body_paths or {}).get(
                source_parent, source_parent))
            body_parent = body_joint
            use_root_follow = False
            if (source_parent.rsplit("|", 1)[-1]
                    .rsplit(":", 1)[-1] == "Root_M"
                    and root_follow_transform is not None):
                body_parent = root_follow_transform
                use_root_follow = True
            legacy_source = (source_parent.rsplit("|", 1)[-1]
                             .rsplit(":", 1)[-1])
            if (follower_sources is None
                    or spec.name in follower_sources
                    or legacy_source in follower_sources):
                follower_key = (
                    legacy_source
                    if follower_sources is not None
                    and spec.name not in follower_sources
                    and legacy_source in follower_sources
                    else spec.name)
                legacy_follower = (follower_sources is not None
                                   and spec.name not in follower_sources
                                   and follower_key == legacy_source)
                if legacy_follower:
                    # Earlier registered characters used one follower per
                    # Body parent, with unfiltered OPM scale or no
                    # non-OPM scale connection. Keep that saved layout.
                    body_parent = body_joint
                    use_root_follow = False
                follower_name = "AdvPy_GenericFKFollow_" + follower_key
                follower_path = root_path + "|" + follower_name
                inherit_scale = (
                    use_offset_parent_matrix if legacy_follower else
                    not fit_segment_scale_compensate(
                        item, spec.name,
                        spec.parent_path.rsplit("|", 1)[-1],
                        use_offset_parent_matrix=use_offset_parent_matrix,
                        is_finger=source_name in finger_names))
                follower = BodyGenericFkFollowerSpec(
                    follower_path, follower_name, body_parent,
                    use_offset_parent_matrix, inherit_scale,
                    use_parent_constraint=(
                        use_root_follow
                        or (legacy_follower
                            and not use_offset_parent_matrix)),
                    scale_source_body_joint=(
                        body_joint if use_root_follow else None))
                if (follower_path in followers
                        and followers[follower_path] != follower):
                    raise ValueError("旧通用 FK 共享跟随层有冲突的父级或缩放设置："
                                     + follower_name)
                followers[follower_path] = follower
                parent_control = follower_path
        if needs_endpoint:
            if parent_control == root_path:
                raise ValueError("Bendy 末端缺少独立的上游 FK 控制："
                                 + spec.name)
            endpoint_name = "AdvPy_" + spec.name + "BendyEndFKX"
            follow_source = None
            if standard_parent:
                ancestor_body = ((remapped_body_paths or {}).get(
                    parent_spec, parent_spec))
                follow_source = (bendy_parent_sources or {}).get(
                    ancestor_body)
                if follow_source is None:
                    raise ValueError("Bendy 末端缺少标准父骨段的独立矩阵："
                                     + spec.name)
            endpoints.append(BodyGenericFkEndpointSpec(
                parent_control + "|" + endpoint_name,
                endpoint_name, parent_control, state.path,
                state.world_position, state.world_axes,
                state.rotation_order,
                *(follow_source or (None, None, None))))
            continue
        stem = spec.name
        offset_name = "AdvPy_" + stem + "FKOffset"
        extra_name = "AdvPy_" + stem + "FKExtra"
        control_name = "AdvPy_" + stem + "FK"
        offset_path = parent_control + "|" + offset_name
        aim_name = (("AdvPy_" + stem + "FKGuideAim")
                    if item.curve_guide is not None else
                    ("AdvPy_" + stem + "FKAim")
                    if (item.aim and spec.path in child_paths
                        and (aim_sources is None
                             or source_leaf in aim_sources)) else None)
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
            source_override_path=(None if spec.path in inbetween_start_paths
                                  else (sub_path or control_path)
                                  + "|AdvPy_" + stem + "FKX"),
            source_override_joint=(
                spec.path not in inbetween_start_paths
                and (fkx_joint_controls is None
                     or control_name in fkx_joint_controls)),
            source_override_segment_scale_compensate=(
                not use_offset_parent_matrix),
            extra_path=extra_path,
            extra_name=extra_name,
            extra_curve=extra_controllers,
            fit_joint_names=tuple(dict.fromkeys((source_leaf, source_name))),
            aim_path=aim_path,
            aim_name=aim_name,
        )
        controls.append(control)
        # The MEL non-OPM FK pass parents ordinary child offsets below the
        # previous FKX joint, so inverseScale participates in the chain.
        control_by_name[spec.name] = (
            control.source_override_path
            if (control.source_override_joint
                and not use_offset_parent_matrix)
            else control_path)
        if item.no_control:
            hidden.append(control_path)
    if follower_sources is not None:
        retained = {follower.name.removeprefix(
            "AdvPy_GenericFKFollow_") for follower in followers.values()}
        missing = follower_sources - retained
        if missing:
            raise ValueError("旧角色通用 FK 跟随层无法从当前 Fit 重建："
                             + "、".join(sorted(missing)))
    return BodyGenericFkPlan(root_path, tuple(controls), tuple(hidden),
                             tuple(followers.values()),
                             finger_visibility_plug,
                             tuple(endpoints))
