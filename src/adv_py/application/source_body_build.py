"""Build source-named Fit skeletons through the shared Body graph primitives.

asFBXRig creates and labels Fit joints, then calls asReBuildAdvancedSkeleton.
The import layer must not own a second implementation of FK, IK or Main.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import dist

from adv_py.core.body_arm_ik import BodyArmIkPlan, plan_body_arm_ik
from adv_py.core.body_limb_mechanisms import (
    BodyLimbMechanismPlan, BodyLimbMechanismRole, plan_body_limb_mechanisms,
    body_limb_parent_matches,
)
from adv_py.core.body_limb_blend import BodyLimbBlendPlan, plan_body_limb_blend
from adv_py.core.body_generic_fk import BodyGenericFkPlan, plan_body_generic_fk
from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.fit_bendy import FitBendyChainSpec, plan_fit_bendy_chains
from adv_py.core.source_body_spline import plan_source_body_splines
from adv_py.core.source_spline_follow import configure_source_spline_follow
from adv_py.core.source_limb_ik_local import configure_source_limb_ik
from adv_py.core.source_body_root import (
    SourceBodyRootPlan, plan_source_body_root, finalize_source_body_root,
)
from adv_py.core.body_character_global import (
    BodyCharacterGlobalPlan, BodyRootFkScaleSpec, plan_body_character_global,
)
from adv_py.core.body_direct_fk_scale import (
    BodyDirectFkScaleSpec, plan_body_direct_fk_scales,
)
from adv_py.core.body_control_spaces import BodyControlSpacesPlan
from adv_py.core.character_registry import CharacterChannel
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_hierarchy import fit_build_scale
from adv_py.core.body_skeleton import (
    BodySkeletonSnapshot, plan_body_non_deform_markers, oriented_body_provenance,
)
from adv_py.core.body_fk_global import BodyFkGlobalSpec, plan_body_fk_global
from adv_py.core.body_fit_aim import BodyFitAimSpec, plan_body_fit_aim
from adv_py.core.body_fk_channel_locks import (
    BodyFkChannelLockSpec, plan_body_fk_channel_locks,
)
from adv_py.core.body_fk_scale_compensation import (
    BodyFkScaleCompensationSpec, plan_body_fk_scale_compensation,
)
from .body_fk_scale_compensation import BuildBodyFkScaleCompensation
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide
from adv_py.core.fit_ik import fit_joint_ik_info
from adv_py.core.joint_labels import JointLabel

from .oriented_body_skeleton import BuildOrientedBodySkeleton
from .character_registry import RegisterBodyCharacter
from .body_selection_sets import finalize_body_character_sets
from .fit_part import BuildFitPartHierarchy
from .source_body_parts import build_source_body_part_drivers
from .source_body_inbetween import build_source_body_inbetween
from .source_body_follow import build_source_body_follow
from .source_body_options import build_source_body_options
from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
from adv_py.core.fit_part_twist import FitPartTwistStep
from adv_py.core.fit_part_scale import FitPartScalePlan


@dataclass(frozen=True, slots=True)
class SourceBodyLimbPlan:
    label: str
    joint_names: tuple[str, ...]
    mechanisms: BodyLimbMechanismPlan
    ik: BodyArmIkPlan
    blend: BodyLimbBlendPlan
    foot: object | None = None
    root_frames: tuple = ()


@dataclass(frozen=True, slots=True)
class SourceBodyRigPlan:
    container: str
    fk: BodyGenericFkPlan
    global_control: BodyCharacterGlobalPlan
    limbs: tuple[SourceBodyLimbPlan, ...]
    control_spaces: BodyControlSpacesPlan
    no_control_paths: tuple[str, ...] = ()
    fk_channel_locks: tuple[BodyFkChannelLockSpec, ...] = ()
    fk_globals: tuple[BodyFkGlobalSpec, ...] = ()
    fit_aim: tuple[BodyFitAimSpec, ...] = ()
    fk_scale_compensations: tuple[BodyFkScaleCompensationSpec, ...] = ()
    spline: BodySplinePlan | None = None
    bendy_chains: tuple[FitBendyChainSpec, ...] = ()
    inbetween_segments: tuple = ()
    twist_steps: tuple[FitPartTwistStep, ...] = ()
    part_scale: FitPartScalePlan | None = None
    part_paths: FitPartFinalPaths | None = None
    fit_follows: tuple = ()
    named_follows: tuple = ()
    follow_spaces: tuple = ()
    ik_follows: tuple = ()
    advanced_constraints: tuple = ()
    aim_at: tuple = ()
    geo_attach: tuple = ()
    proximity_pin: tuple = ()
    wheels: tuple = ()
    curve_guides: tuple = ()
    tweakers: object | None = None
    additional_splines: tuple[BodySplinePlan,...] = ()
    root: SourceBodyRootPlan | None = None
    center_between_feet: object | None = None
    internal_ik_local: tuple = ()
    hip_swing: object | None = None
    rp_dynamics: tuple = ()
    leg_aim: tuple = ()
    source_rp_scale_axes: bool = True
    source_use_offset_parent_matrix: bool = True
    rp_follows: tuple = ()

    @property
    def all_splines(self):
        return ((self.spline,) if self.spline is not None else ()) + self.additional_splines


@dataclass(frozen=True, slots=True)
class SourceBodyRigResult:
    plan: SourceBodyRigPlan
    body: BodySkeletonSnapshot


def source_body_limb_chains(body, labels, hierarchy):
    """Use the original Fit label query and its ancestor/descendant order."""
    by_name = {joint.name: joint for joint in body.joints}
    by_fit_path = {node.path: node for node in hierarchy.joints}
    label_by_name = dict(labels)
    if len(label_by_name) != len(labels):
        raise FitSkeletonValidationError("来源 Fit 标签名称重复")
    fit_labels = {node.path: (JointLabel.parse(label_by_name[name])
                             if name in label_by_name else None)
                  for node in hierarchy.joints
                  for name in (node.short_name.rsplit(":", 1)[-1],)}
    chains = []
    used = set()
    labels_seen = {}
    for node in hierarchy.joints:
        label = fit_labels[node.path]
        if label is None or not ("Shoulder" in label.text or "Hip" in label.text):
            continue
        info = fit_joint_ik_info(hierarchy, fit_labels, node.path)
        if info is None or info.start != node.path:
            continue
        from adv_py.core.source_fit_identity import source_fit_build_name
        names = tuple(source_fit_build_name(by_fit_path[path].short_name)
                      for path in info.joints)
        if len(names) < 2:
            continue
        if info.name in labels_seen:
            if labels_seen[info.name]==names:
                continue  # Authored non-symmetry is the same source system.
            raise FitSkeletonValidationError("来源 IK 系统名称重复：" + info.name)
        paths = set()
        for suffix in ("R", "L", "M"):
            chain = tuple(by_name.get(name + "_" + suffix) for name in names)
            if chain[0] is None:
                continue
            if any(joint is None for joint in chain):
                raise FitSkeletonValidationError("来源 IK 标签缺少对应侧：" + info.name)
            if any(not body_limb_parent_matches(child.parent_path, parent.path,
                    allow_part_parents=True)
                   for parent, child in zip(chain, chain[1:])):
                raise FitSkeletonValidationError("来源 IK 标签父链不完整：" + info.name)
            paths.update(joint.path for joint in chain)
        if not paths:
            raise FitSkeletonValidationError("来源 IK 标签没有实际 Body 起点："+info.name)
        if paths & used:
            raise FitSkeletonValidationError("来源 IK 链共享关节：" + info.name)
        used.update(paths)
        labels_seen[info.name]=names
        chains.append((info.name, names))
    return tuple(chains)


def source_character_channels(rig):
    p = rig.plan
    rows = []
    locked = {spec.control: frozenset(spec.attributes)
              for spec in p.fk_channel_locks}
    trs = tuple(kind + axis for kind in ("translate", "rotate", "scale")
                for axis in "XYZ")
    def add(key, node, attributes):
        rows.extend(CharacterChannel(key + "." + attribute, node, attribute)
                    for attribute in attributes
                    if attribute not in locked.get(node, ()))
    add("global", p.global_control.control_path,
        tuple(kind + axis for kind in ("translate", "rotate") for axis in "XYZ")
        + (p.global_control.scale_attribute,)
        + (tuple("scale"+axis for axis in "XYZ") if p.global_control.native_scale_channels else ()))
    for index, node in enumerate(p.global_control.extra_control_paths, 1):
        add(f"global.extra.{index}", node, trs)
    if p.root is not None:
        root_tr = tuple(kind+axis for kind in ('translate','rotate') for axis in 'XYZ')
        for key, control in (("root.x",p.root.root_x), *(
                (f"root.cog.{index}",control) for index,control in enumerate(p.root.cogs))):
            add(key,control.control_path,root_tr)
            add(key+'.extra',control.extra_path,root_tr)
        if p.root.leg_lock_enabled:
            add('root.fk',p.root.fk_control,('legLock',))
        if p.center_between_feet is not None:
            add('root.x',p.root.root_x.control_path,('centerBetweenFeet',))
    for spec in p.internal_ik_local:
        add('source.ik.local.'+spec.control_name,spec.control_path,
            tuple(kind+axis for kind in ('translate','rotate','scale') for axis in 'XYZ'))
        add('source.ik.local.'+spec.control_name+'.extra',spec.extra_path,
            tuple(kind+axis for kind in ('translate','rotate') for axis in 'XYZ'))
    for spec in p.rp_dynamics:
        key='source.rp.'+spec.label+'.'+spec.side
        add(key,spec.control,('stretchy','antiPop','volume')+
            tuple(segment.length_attribute for segment in spec.segments)+
            tuple(segment.fatness_attribute for segment in spec.segments))
        add(key+'.pole',spec.pole,('lock',))
    for plan in p.rp_follows:
        foot_swivel=any(side.ankle_control_path==plan.control and 'swivel' in side.attributes
                        for limb in p.limbs if limb.foot for side in limb.foot.sides)
        if not foot_swivel:
            add('source.rp.swivel.'+plan.control.rsplit('|',1)[-1],plan.control,('swivel',))
        for spec in plan.spaces:
            add('source.rp.follow.'+spec.fk_control.rsplit('|',1)[-1],spec.fk_control,
                tuple('follow'+target.label for target in spec.targets))
    for spec in p.leg_aim:
        add('source.legAim.'+spec.label+'.'+spec.side,spec.control,('legAim',))
    if p.hip_swing is not None:
        add('source.hipSwing',p.hip_swing.control_path,tuple('rotate'+axis for axis in 'XYZ'))
    for control in p.fk.controls:
        key = "generic.fk." + control.control_name.removeprefix("AdvPy_")
        add(key, control.control_path, trs)
        if control.sub_control_path:
            add(key, control.control_path, ("subControl",))
            add(key + ".sub", control.sub_control_path, trs)
        if control.extra_path:
            if control.extra_curve:
                add(key, control.control_path, ("extraControl",))
            add(key + ".extra", control.extra_path, trs)
    for spline in p.all_splines:
        spline_key='source.spline'+('.'+spline.system_name if spline.system_name else '')
        for index, target in enumerate(spline.targets):
            attributes = (() if index == 0 and not spline.source_first_translate else tuple("translate" + axis for axis in "XYZ"))
            if index in (0, len(spline.targets) - 1) or spline.twist_ramp_graph or spline.source_first_translate:
                attributes += tuple("rotate" + axis for axis in "XYZ")
            attributes += tuple("scale" + axis for axis in "XYZ")
            if spline.mid_follow_graph and 0 < index < len(spline.targets) - 1:
                attributes += ("followEnd",)
            key = f"{spline_key}.{index}"
            add(key, target, attributes)
            if spline.extra_targets:
                add(key + ".extra", spline.extra_targets[index], trs)
                if spline.extra_curve:
                    add(key, target, ("extraControl",))
            if spline.sub_targets:
                add(key, target, ("subControl",))
                add(key + ".sub", spline.sub_targets[index], trs)
        add(spline_key,spline.mode_control,(spline.mode_attribute,))
        add(spline_key, spline.settings,
            ("stretchy", "volume", "stretchEven", "noFlipAxis"))
        add(spline_key+'.0',spline.targets[0],('firstJointFixed',))
        if spline.source_curve_points:
            add(spline_key, spline.settings, ("ikCvVis",))
            add(spline_key,spline.visibility_settings,("autoVis","FKVis","IKVis"))
            for index, control in enumerate(spline.cv_controls, 1):
                add(f"{spline_key}.cv.{index}", control,
                    tuple("translate"+axis for axis in "XYZ"))
            if len(spline.source_curve_points)>3:
                for index in (0,len(spline.targets)-1):
                    add(f"{spline_key}.{index}", spline.targets[index], ("stiff",))
        if spline.source_hybrid_graph:
            add(spline_key,spline.settings,("ikHybridVis",))
            for index,control in enumerate(spline.hybrid_controls):
                add(f"{spline_key}.hybrid.{index}",control,
                    tuple(kind+axis for kind in ("translate","rotate") for axis in "XYZ"))
        for layer_kind,paths in (("cv",spline.cv_extras),("hybrid",spline.hybrid_extras)):
            for index,path in enumerate(paths):
                add(f"{spline_key}.{layer_kind}.extra.{index}",path,
                    tuple(kind+axis for kind in ("translate","rotate") for axis in "XYZ"))
        if spline.source_follow_parent:
            add(spline_key,spline.settings,
                tuple('follow'+label for label,_,_ in spline.source_follow_targets))
    for spec in p.fk_globals:
        key = "generic.global." + spec.control.rsplit("|", 1)[-1]
        add(key, spec.control, ("Global",) + (("GlobalTranslate",) if spec.translate else ()))
    for spec in p.fit_aim:
        key = "generic.aim." + spec.stem
        add(key, spec.center_control, trs + ("follow",))
        for side in spec.sides:
            if side.target_control != spec.center_control:
                add(key + "." + side.suffix, side.target_control, trs)
    for limb in p.limbs:
        if limb.foot is not None:
            for side in limb.foot.sides:
                key='source.foot.'+limb.label+'.'+side.side.value
                add(key,side.ankle_control_path,side.attributes)
                if side.hybrid is None:
                    add(key+'.toe',side.toe_control_path,trs)
                    if side.toe_sub_path:
                        add(key+'.toe.sub',side.toe_sub_path,trs)
                        add(key+'.toe',side.toe_control_path,('subControl',))
                    if side.toe_extra_path:
                        add(key+'.toe.extra',side.toe_extra_path,
                            tuple(kind+axis for kind in ('translate','rotate') for axis in 'XYZ'))
                        if side.toe_extra_curve:
                            add(key+'.toe',side.toe_control_path,('extraControl',))
                for pivot in side.pivots:
                    if pivot.roll_control_path:
                        add(key+'.roll.'+pivot.roll_control_name,pivot.roll_control_path,trs)
                        add(key+'.roll.extra.'+pivot.roll_control_name,pivot.roll_extra_path,
                            tuple(kind+axis for kind in ('translate','rotate') for axis in 'XYZ'))
                for pivot in side.manual_pivots:
                    add(key+'.pivot.'+pivot.control_name,pivot.control_path,trs)
                if side.hybrid:
                    for segment in side.hybrid.segments:
                        add(key+'.hybrid.'+segment.control_name,segment.control_path,trs)
        for spec in limb.ik.limbs:
            key = limb.label.lower() + "." + spec.side.value
            add(key + ".ik", spec.wrist_control_path, trs)
            add(key + ".pole", spec.pole_control_path,
                tuple("translate" + axis for axis in "XYZ"))
            if spec.wrist_sub_path:
                add(key + ".ik", spec.wrist_control_path, ("subControl",))
                add(key + ".ik.sub", spec.wrist_sub_path, trs)
            if spec.wrist_extra_curve:
                add(key + ".ik", spec.wrist_control_path, ("extraControl",))
            if spec.ik_local_mode=='addCtrl':
                add(key+'.ik.local',spec.source_local_control,
                    tuple('rotate'+axis for axis in 'XYZ'))
                add(key+'.ik.local.extra',spec.source_local_extra,
                    tuple(kind+axis for kind in ('translate','rotate') for axis in 'XYZ'))
            for layer, node in (("ik.extra", spec.wrist_extra_path),
                                ("pole.extra", spec.pole_extra_path)):
                if node:
                    add(key + "." + layer, node,
                        tuple(kind+axis for kind in ('translate','rotate') for axis in 'XYZ')
                        if spec.source_aligned_graph else trs)
        for side in limb.blend.sides:
            add(limb.label.lower() + "." + side.side.value,
                limb.blend.settings_path, (side.attribute,))
    for spec in p.fit_follows:
        attributes = ("follow",) + (("followLeftRight",) if spec.opposite_target else ())
        attributes += (("followWorld",) if spec.world_target else ())
        add("fk.follow." + spec.fk_control.rsplit("|",1)[-1], spec.fk_control, attributes)
    for spec in p.named_follows:
        add("fk.follow_by_name." + spec.fk_control.rsplit("|",1)[-1], spec.fk_control,
            tuple("follow"+target.name for target in spec.targets))
    for spec in p.follow_spaces:
        add("fk.follow_space." + spec.fk_control.rsplit("|",1)[-1], spec.fk_control,
            tuple("follow"+target.label for target in spec.targets))
    for spec in p.ik_follows:
        add("ik.follow." + spec.fk_control.rsplit("|",1)[-1], spec.fk_control,
            (spec.control_attribute,))
    for spec in p.advanced_constraints:
        add("fk.constraint." + spec.fk_control.rsplit("|",1)[-1],
            spec.fk_control, (spec.attribute,))
    for specs, key, attribute in ((p.aim_at,"fk.aim_at","aimAt"),
                                  (p.geo_attach,"fk.geo_attach","attach"),
                                  (p.proximity_pin,"fk.proximity_pin","pin")):
        for spec in specs:
            add(key + "." + spec.fk_control.rsplit("|",1)[-1],
                spec.fk_control, (attribute,))
    return tuple(rows)


def build_source_body_character(host, container, *, labels=(), scene_before=None,
                                include_dynamic=True, defer_selection_sets=False,
                                defer_all_set=False, retain_markers=False, defer_registration=False,
                                generic_fk_policy=None, use_fit_part_hierarchy=True):
    """Internal branch of BuildRegisteredBodyCharacter, in its transaction."""
    from .registered_body_build import RegisteredBodyBuildResult
    deformation = host.create_body_system_hierarchy(include_dynamic=include_dynamic)
    fit = host.parent_fit_skeleton_under_group(container)
    skeleton = BuildOrientedBodySkeleton(host).apply(
        fit, root_parent_path=deformation)
    build = skeleton.plan.build
    # Inbetween is a separate source expansion, not a twistJoints variant.
    # Merge both original Part families before any physical reparenting.
    from .fit_inbetween import PrepareFitInbetween
    from .fit_inbetween_body import plan_combined_part_hierarchy
    _, inbetween_plan = PrepareFitInbetween(host).plan(fit)
    if inbetween_plan.guides:
        build = plan_combined_part_hierarchy(build, inbetween_plan)
        skeleton = replace(skeleton, plan=replace(skeleton.plan, build=build))
    part_result = None
    if not use_fit_part_hierarchy and build.fit_parts:
        raise FitSkeletonValidationError("来源 Fit 已标记分段，不能关闭 Part 层级构建")
    if use_fit_part_hierarchy and build.fit_parts:
        host.prepare_fit_part_twist_runtime()
        part_result = BuildFitPartHierarchy(host).apply(build)
        body = part_result.body
        skeleton = replace(skeleton, snapshot=body)
    else:
        body = skeleton.snapshot
    options = build.build_options
    metadata = build.symmetry.source.metadata
    from adv_py.core.fit_inbetween_hip_swing import plan_hip_swing_fit_selection
    hip_selection=plan_hip_swing_fit_selection(build.symmetry.source,allow_missing_child=True)
    scale = fit_build_scale(build.symmetry.source.hierarchy)
    limbs = []
    from adv_py.core.source_body_foot import source_foot_roles,source_foot_joint_names,plan_source_body_foot
    for label, names in source_body_limb_chains(body, labels, build.symmetry.source.hierarchy):
        body_names = {joint.name for joint in body.joints}
        sides = tuple(side for side in (FitBuildSide.RIGHT,FitBuildSide.LEFT,FitBuildSide.MIDDLE)
                      if names[0]+"_"+side.value in body_names)
        foot_roles=source_foot_roles(body,names[-1],sides)
        mechanism_names=source_foot_joint_names(names,foot_roles)
        mechanisms = plan_body_limb_mechanisms(
            body, limb_label=label, joint_names=mechanism_names, allow_part_parents=True,sides=sides)
        from adv_py.core.source_limb_root_frame import configure as configure_root_frames
        mechanisms,root_frames=(configure_root_frames(mechanisms,body) if options.use_offset_parent_matrix else (mechanisms,()))
        ik = plan_body_arm_ik(body, mechanisms, joint_names=names,
            limb_label=label, radius=scale * 1.5,
            sub_controllers=options.sub_controllers,
            extra_controllers=options.extra_controllers,sides=sides,allow_two_joint=True,
            source_pole_placement=generic_fk_policy is None
            or generic_fk_policy.source_rp_build_pole is not False)
        ik = configure_source_limb_ik(ik,mechanisms,body,metadata,names[-1],
            instances=build.symmetry.instances,source_pole_placement=generic_fk_policy is None
            or generic_fk_policy.source_rp_build_pole is not False)
        blend = plan_body_limb_blend(body, mechanisms, limb_label=label,
            joint_names=mechanism_names, translated_joint_names=mechanism_names,sides=sides)
        limb=SourceBodyLimbPlan(label,names,mechanisms,ik,blend)
        foot=plan_source_body_foot(body,limb,foot_roles,metadata,base_radius=scale*1.5,
                                  instances=build.symmetry.instances)
        limbs.append(replace(limb,foot=foot,root_frames=root_frames))
    driver_by_body = {joint.source_joint: joint.path for limb in limbs
                      for joint in limb.mechanisms.joints
                      if joint.role is BodyLimbMechanismRole.FK}
    labels_by_name = dict(labels)
    labels_by_path = {node.path: (JointLabel.parse(labels_by_name[name])
                                if name in labels_by_name else None)
                      for node in build.symmetry.source.hierarchy.joints
                      for name in (node.short_name.rsplit(":", 1)[-1],)}
    ik_end_paths = set()
    fit_ik_infos = {}
    for node in build.symmetry.source.hierarchy.joints:
        info = fit_joint_ik_info(build.symmetry.source.hierarchy,
                                labels_by_path, node.path)
        fit_ik_infos[node.path]=info
        if info is not None and info.start == node.path:
            ik_end_paths.add(info.end)
    fit_hierarchy=build.symmetry.source.hierarchy
    fit_root_children=tuple(node.path for node in fit_hierarchy.joints
        if node.dag_parent is not None and node.dag_parent.rsplit('|',1)[-1].rsplit(':',1)[-1]=='Root')
    first_after_ik_sources=set()
    for node in fit_hierarchy.joints:
        parent_info=fit_ik_infos.get(node.dag_parent)
        own_info=fit_ik_infos.get(node.path)
        if (parent_info is not None and
                (own_info is None or own_info.name!=parent_info.name)
                or node.path in fit_root_children[1:]):
            first_after_ik_sources.add(node.path)
    bendy_chains = (plan_fit_bendy_chains(
        tuple(part for part in build.fit_parts if part.kind == "twist"),
        metadata, build.specs) if part_result is not None else ())
    if bendy_chains:
        bendy_chains = rebase_plan_paths_after_parts(bendy_chains, part_result.final_paths)
        axes = {joint.path: joint.world_axes for joint in body.joints}
        bendy_chains = tuple(replace(chain,
            start_world_axes=axes[chain.start_body],
            # MEL 83741 reads child.tx before OPM Part reparenting shortens
            # the terminal local segment. Preserve that full bind span.
            falloff_span=(dist(chain.start_position, chain.end_position)
                          if options.use_offset_parent_matrix else
                          host.capture_fit_bendy_end_local_length(chain.end_body)),
            scale_guide_group=not options.use_offset_parent_matrix,
            non_opm_additive_micro_scale=not options.use_offset_parent_matrix,
            opm_offset_only_scale=options.use_offset_parent_matrix,
            source_deform_matrix=options.use_offset_parent_matrix and (
                generic_fk_policy is None or generic_fk_policy.source_bendy_deform_matrix is not False),
            secondary_matrix_follow=True, mel_main_influence_follow=True)
            for chain in bendy_chains)
    fk_metadata = tuple(replace(item, control=True)
                        if item.joint in ik_end_paths else item
                        for item in metadata)
    fk = plan_body_generic_fk(body, build.specs, fk_metadata, (),
        sub_controllers=options.sub_controllers,
        extra_controllers=options.extra_controllers,
        radius=scale * 1.5,
        bendy_end_paths=frozenset(chain.end_body for chain in bendy_chains),
        inbetween_start_paths=frozenset(part.start_body for part in build.fit_parts
            if part.kind == "inbetween"),
        aim_sources=(generic_fk_policy.aim_sources if generic_fk_policy else None),
        follower_sources=(generic_fk_policy.follower_sources if generic_fk_policy else None),
        fkx_joint_controls=(generic_fk_policy.fkx_joint_controls if generic_fk_policy else None),
        point_controls=(generic_fk_policy.point_controls if generic_fk_policy else None),
        remapped_body_paths=(dict(part_result.final_paths.body_rewrites)
                            if part_result is not None else None),
        root_follow_transform='|Group|MotionSystem|RootSystem|AdvPy_LegLockConstrained',
        first_after_ik_paths=frozenset(spec.path for spec in build.specs
            if spec.source_joint in first_after_ik_sources),
        use_offset_parent_matrix=options.use_offset_parent_matrix,
        follow_inserted_parts=False)
    fk = replace(fk, controls=tuple(replace(control,
        driven_joint=driver_by_body.get(control.driven_joint, control.driven_joint))
        for control in fk.controls))
    if (generic_fk_policy is not None and generic_fk_policy.source_spline_layouts is not None
            and generic_fk_policy.source_spline_body_root is not None):
        from adv_py.core.fit_part import FitPartFinalPaths
        saved_paths=FitPartFinalPaths((),(),((generic_fk_policy.source_spline_body_root,body.root),))
        generic_fk_policy=replace(generic_fk_policy,source_spline_layouts=rebase_plan_paths_after_parts(
            generic_fk_policy.source_spline_layouts,saved_paths),source_spline_body_root=body.root)
    fk, splines = plan_source_body_splines(body, build.symmetry.source.hierarchy,
        labels, fk, options, metadata,instances=build.symmetry.instances,
        saved_layouts=generic_fk_policy.source_spline_layouts if generic_fk_policy else None,
        control_counts=generic_fk_policy.source_spline_counts if generic_fk_policy else (),parts=build.fit_parts)
    root = plan_source_body_root(body,fk,metadata,build.symmetry.instances,options,
                                 base_radius=scale*1.5)
    if generic_fk_policy is not None and generic_fk_policy.source_leg_lock_opm is False:
        root=replace(root,leg_lock_opm=False)
    root=replace(root,hip_swing_no_parts=bool(hip_selection and hip_selection.enabled
                                           and not hip_selection.root_inbetween_count))
    original_by_driver=dict((joint.path,joint.source_joint) for spline in splines
                            for joint in spline.joints)
    original_by_driver.update((driver,source) for source,driver in driver_by_body.items())
    root_children=tuple(joint.path for joint in body.joints if joint.parent_path==body.root)
    from adv_py.core.source_part_reference import source_root_primary_child
    primary_child=source_root_primary_child(build.symmetry.source.hierarchy,
                                           build.symmetry.source.fit_scale)
    first_child=next((spec.path for spec in build.specs
                      if primary_child is not None and spec.source_joint==primary_child.path
                      and spec.path in root_children),None)
    root = replace(root,branch_offsets=tuple(control.offset_path for control in fk.controls
        if original_by_driver.get(control.driven_joint,control.driven_joint) in root_children
        and original_by_driver.get(control.driven_joint,control.driven_joint)!=first_child
        and control.parent_path.startswith(root.fk_control+'|')))
    host.create_source_body_root_controls(root)
    splines=tuple(host.capture_source_body_spline_positions(spline) for spline in splines)
    if splines:
        root_parent, root_name = fk.root_path.rsplit("|", 1)
        if host.create_body_control_root(root_name, parent_path=root_parent) != fk.root_path:
            raise RuntimeError("来源 Spline 的 FK 根路径漂移")
        for spline in splines:
            host.prepare_source_body_spline(spline)
    for limb in limbs:
        if host.create_body_arm_mechanism_root(limb.mechanisms.root_name) != limb.mechanisms.root_path:
            raise RuntimeError("来源机制链根路径漂移")
        for frame in limb.root_frames:
            host.create_source_limb_root_frame(frame)
        for joint in limb.mechanisms.joints:
            if host.create_body_arm_mechanism_joint(joint) != joint.path:
                raise RuntimeError("来源机制关节路径漂移：" + joint.name)
        if limb.root_frames:host.finalize_source_limb_root_frames(limb.root_frames)
    host.create_body_generic_fk(fk, root_prepared=bool(splines))
    host.connect_source_body_root_fk(root)
    updated_limbs=[]
    for limb in limbs:
        if host.create_body_arm_ik_root(limb.ik.root_name) != limb.ik.root_path:
            raise RuntimeError("来源 IK 控制根路径漂移")
        for spec in limb.ik.limbs:
            host.create_body_arm_ik(spec)
        host.create_body_arm_blend(limb.blend)
        host.connect_source_body_limb_follow(body, limb.mechanisms,
                                            root_follow_path=root.leg_lock_path,root_frames=limb.root_frames)
        host.connect_source_body_limb_visibility(limb, fk)
        host.connect_source_body_limb_scales(limb,
            use_offset_parent_matrix=options.use_offset_parent_matrix,
            source_scale_axes=generic_fk_policy is None or generic_fk_policy.source_rp_scale_axes is not False)
        if limb.foot is not None:
            limb=replace(limb,foot=replace(limb.foot,sides=tuple(
                host.capture_source_body_foot_align_frames(side,limb.ik.limbs)
                for side in limb.foot.sides)))
            for side in limb.foot.sides:
                host.create_body_leg_foot_side(side)
            limb=replace(limb,ik=replace(limb.ik,limbs=tuple(replace(spec,
                source_handle_parent=next(side.final_handle_parent_path
                    for side in limb.foot.sides if side.side is spec.side),
                source_foot_matrix=next(side.source_end_world_matrix+'.matrixSum'
                    for side in limb.foot.sides if side.side is spec.side)) for spec in limb.ik.limbs)))
        updated_limbs.append(limb)
    limbs=updated_limbs
    roots = ("|Group|MotionSystem|FKSystem", fk.root_path) + tuple(limb.ik.root_path for limb in limbs)
    roots += tuple(limb.mechanisms.root_path for limb in limbs)
    root_metadata = next(item for item in metadata
                         if item.joint == build.specs[0].source_joint)
    root_control = next(control for control in fk.controls
                        if control.driven_joint == body.root)
    global_control = plan_body_character_global(
        up_axis=FitUpAxis.Y, body_root=body.root, driven_roots=roots,
        fit_height=body.fit_height,
        scale_destinations=tuple(body.root + ".scale" + axis for axis in "XYZ"),
        radius=scale * 12, body_root_via_controls=True,
        root_fk_scale=BodyRootFkScaleSpec(body.root, root_control.control_path + ".scale"),
        num_main_extras=root_metadata.num_main_extras or 0,
        root_follow_main_path="|Group|MotionSystem|RootSystem|RootFollowMain",
        root_follow_use_opm=options.use_offset_parent_matrix,
        global_follow_main_path="|Group|MotionSystem|GlobalSystem|GlobalFollowMain",
        global_follow_use_opm=options.use_offset_parent_matrix)
    host.create_body_character_global(global_control)
    fk,limbs,root,splines,global_control,generic_fk_policy,leg_aim = host.create_source_limb_aim(
        body,fk,limbs,root,splines,global_control,generic_fk_policy,build.symmetry.instances,
        options.use_offset_parent_matrix)
    splines=tuple(configure_source_spline_follow(spline,body,fk,global_control,
        root_control_path=root.root_x.control_path,root_follow_path=root.leg_lock_path)
        for spline in splines)
    if generic_fk_policy is not None and generic_fk_policy.source_spline_layouts is not None:
        from adv_py.core.source_spline_rebuild import saved_source_spline_layout,retain_source_spline_layout
        splines=tuple(retain_source_spline_layout(spline,saved_source_spline_layout(
            spline.body_joints,generic_fk_policy.source_spline_layouts),
            change_count=spline.system_name in dict(generic_fk_policy.source_spline_counts)) for spline in splines)
    for spline in splines:
        host.create_source_body_spline(spline)
        host.connect_source_body_spline_visibility(spline,fk)
    scales = list(plan_body_direct_fk_scales(body, fk.controls))
    scales.extend(BodyDirectFkScaleSpec(control.driven_joint,
                  control.control_path + ".scale") for control in fk.controls
                  if control.driven_joint in driver_by_body.values())
    if generic_fk_policy is not None and generic_fk_policy.scale_controls is not None:
        scales = [spec for spec in scales
                  if spec.source_scale.removesuffix(".scale") in generic_fk_policy.scale_controls]
    for spec in scales:
        host.preflight_body_direct_fk_scale(spec)
        host.connect_body_direct_fk_scale(spec)
    generated_sources = tuple((driver, source) for source, driver in driver_by_body.items())
    for spline in splines:
        generated_sources += tuple((joint.path, joint.source_joint)
                                   for joint in spline.joints
                                   if joint.role is BodyLimbMechanismRole.FK)
    if part_result is not None:
        original_by_current = {after: before for before, after
                               in part_result.final_paths.body_rewrites}
        generated_sources = tuple((driver, original_by_current.get(source, source))
                                  for driver, source in generated_sources)
    compensation = plan_body_fk_scale_compensation(
        fk.controls, build.symmetry.instances, metadata,
        use_offset_parent_matrix=options.use_offset_parent_matrix,
        generated_joint_sources=generated_sources)
    if part_result is not None:
        compensation = rebase_plan_paths_after_parts(compensation, part_result.final_paths)
        # The next FK Offset is driven by the last Inbetween FKX. A second
        # generic TRS/OPM compensation writer would occupy that same receiver.
        inbetween_ends = {part_result.final_paths.remap_body_reference(part.end_body)
                         for part in build.fit_parts if part.kind == "inbetween"}
        part_follow_controls = {control.control_path for control in fk.controls
            if original_by_driver.get(control.driven_joint, control.driven_joint)
            in inbetween_ends}
        compensation = tuple(spec for spec in compensation
                             if spec.control_path not in part_follow_controls)
    if generic_fk_policy is not None and generic_fk_policy.compensated_controls is not None:
        compensation = tuple(spec for spec in compensation
                             if spec.control_path in generic_fk_policy.compensated_controls)
    if options.use_offset_parent_matrix:
        compensation=tuple(replace(spec,independent_parent=True,
            main_scale_source_path=global_control.control_path) for spec in compensation)
    BuildBodyFkScaleCompensation(host).apply(compensation)
    fk, limbs, inbetween_segments, solver_mapping = build_source_body_inbetween(
        host, build, part_result, fk, limbs, splines,
        source_untwister_receiver=generic_fk_policy is None
        or generic_fk_policy.source_untwister_receiver is not False)
    root = finalize_source_body_root(root,fk,splines,inbetween_segments)
    host.connect_source_body_root_outputs(root,body,fk,splines,generated_sources)
    from .source_body_hip_swing import build_source_hip_swing
    hip_swing=build_source_hip_swing(host,hip_selection,root,body,fk,
                                   inbetween_segments,build.fit_parts)
    from adv_py.core.source_limb_ik_local import plan_source_internal_ik_local
    internal_ik_local=plan_source_internal_ik_local(body,fk,limbs,metadata,instances=build.symmetry.instances)
    for spec in internal_ik_local:
        host.create_source_internal_ik_local(spec)
    rp_dynamics=(host.create_source_rp_dynamics(body,limbs,global_control,
        internal_ik_local,root.leg_lock_path,source_pole_targets=generic_fk_policy is None
        or generic_fk_policy.source_rp_pole_sources is not False,
        source_x_translation=generic_fk_policy is None or generic_fk_policy.source_rp_x_translation is not False,
        source_part_scale=generic_fk_policy is None or generic_fk_policy.source_rp_part_scale is not False,
        instances=build.symmetry.instances,inbetween_segments=inbetween_segments) if generic_fk_policy is None
        or generic_fk_policy.source_rp_dynamics is not False else ())
    center_between_feet = None
    if root.center_between_feet:
        from adv_py.core.body_center_between_feet import plan_source_center_between_feet
        center_between_feet = plan_source_center_between_feet(root.root_x,tuple(
            spec.wrist_control_path for limb in limbs if 'Leg' in limb.label
            for spec in limb.ik.limbs))
        state = host.preflight_body_center_between_feet(center_between_feet)
        host.create_body_center_between_feet(center_between_feet,state)
    fk_globals = plan_body_fk_global(metadata, fk.controls)
    if generic_fk_policy is not None and generic_fk_policy.global_controls is not None:
        fk_globals = tuple(spec for spec in fk_globals
                           if spec.control in generic_fk_policy.global_controls)
    for spec in fk_globals:
        host.create_body_fk_global(spec)
    aim_controls = tuple(control for control in fk.controls if control.aim_path is not None)
    aim_names = {name for control in aim_controls for name in control.fit_joint_names}
    fit_aim = plan_body_fit_aim(build.symmetry.source.hierarchy,
        tuple(item for item in metadata
              if item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1] in aim_names),
        body, aim_controls)
    for spec in fit_aim:
        host.create_body_fit_aim(spec, global_control=global_control.control_path,
            use_offset_parent_matrix=options.use_offset_parent_matrix)
    if not retain_markers:
        markers = plan_body_non_deform_markers(body)
        if markers:
            body = host.remove_body_non_deform_markers(body.root, markers)
            skeleton = replace(skeleton, snapshot=body)
    twist_steps, part_scale, bendy_chains = build_source_body_part_drivers(
        host, build, part_result, fk, limbs, splines, bendy_chains, inbetween_segments)
    (fit_follows, named_follows, follow_spaces, ik_follows,
     advanced_constraints, aim_at, geo_attach, proximity_pin) = build_source_body_follow(
        host, metadata, body, fk, limbs, splines, global_control,
        root_control_path=root.root_x.control_path)
    rp_follows=host.create_source_rp_follows(body,limbs,global_control,root,leg_aim=leg_aim)
    fk, wheels, curve_guides, tweakers = build_source_body_options(
        host, build, body, fk, limbs, splines, global_control, part_result)
    # Wheel creates its final FKX receiver through the existing constraints.
    # Convert Body matrices only after that handoff selects the actual driver.
    if (options.use_offset_parent_matrix and
            (generic_fk_policy is None or generic_fk_policy.source_body_matrix is not False)):
        from adv_py.core.source_fit_identity import source_fit_metadata
        excluded=frozenset(chain.start_body for chain in bendy_chains)
        excluded|=frozenset(joint.path for joint in body.joints
            if (item:=source_fit_metadata(joint.name,metadata,build.symmetry.instances)) is not None
            and item.rolling_ball)
        rp_dynamics=host.create_source_body_matrices(body,fk,limbs,rp_dynamics,excluded=excluded)
        splines=host.create_source_spline_body_matrices(body,fk,splines,excluded=excluded,
            saved_layouts=generic_fk_policy.source_spline_layouts if generic_fk_policy else None)
        host.create_source_fk_body_matrices(body,fk,excluded=excluded|frozenset(
            joint for spline in splines for joint in spline.body_joints),
            include_root=generic_fk_policy is None or generic_fk_policy.source_root_body_matrix is not False)
    if options.use_offset_parent_matrix:
        host.create_source_inbetween_fk_matrices(fk,inbetween_segments,global_control,metadata,build.symmetry.instances)
        host.create_source_spline_part_matrices(body,splines,inbetween_segments)
        host.create_source_fk_part_matrices(inbetween_segments)
    # MEL selects initial IK by the actual end label containing Foot;
    # a Hip/Leg system ending in Toes alone keeps its default FK mode.
    initial_ik = tuple(limb for limb in limbs
        if "Foot" in labels_by_name.get(limb.joint_names[-1], ""))
    for limb in initial_ik:
        host.set_body_leg_initial_ik(limb.blend)
    if (bendy_chains or fit_follows or named_follows or follow_spaces or ik_follows
            or advanced_constraints or aim_at or geo_attach or proximity_pin
            or wheels or curve_guides or initial_ik or root is not None
            or tweakers is not None and tweakers.controls):
        body = host.capture_body_skeleton(body.root)
    provenance = oriented_body_provenance(fit, len(body.joints))
    from adv_py.core.body_skeleton import audit_body_provenance
    issues = audit_body_provenance(provenance, body.provenance)
    if issues:
        raise FitSkeletonValidationError("来源 Body 最终归属记录不一致："
            + "；".join(issue.message for issue in issues))
    # The oriented skeleton owns this record already; removing temporary
    # foot markers updates its locked count without recreating attributes.
    skeleton = replace(skeleton, snapshot=body,
                       plan=replace(skeleton.plan, provenance=provenance))
    lock_specs = plan_body_fk_channel_locks(
        build.symmetry.source.hierarchy, fk.controls,
        tuple((node.path, host.read_fit_fk_lock_channels(node.path))
              for node in build.symmetry.source.hierarchy.joints))
    for spec in lock_specs:
        host.apply_body_fk_channel_locks(spec)
    rig_plan = SourceBodyRigPlan(fit, fk, global_control, tuple(limbs),
        BodyControlSpacesPlan(body.root, ()), fk.hidden_controls, lock_specs,
        fk_globals, fit_aim, compensation, splines[0] if splines else None, bendy_chains, inbetween_segments,
        twist_steps, part_scale, part_result.final_paths if part_result is not None else None,
        fit_follows, named_follows, follow_spaces, ik_follows,
        advanced_constraints, aim_at, geo_attach, proximity_pin,
        wheels, curve_guides, tweakers, splines[1:],root,center_between_feet,internal_ik_local,hip_swing,rp_dynamics,leg_aim,
        generic_fk_policy is None or generic_fk_policy.source_rp_scale_axes is not False,options.use_offset_parent_matrix,rp_follows)
    rig = SourceBodyRigResult(rig_plan, body)
    # ADV gives implicitly created unit conversions their final names at
    # the end of construction. Freeze those names before capturing registry
    # input plugs, even when Skin/AllSet completion is deferred by the caller.
    from adv_py.core.body_all_set import BodyAllSetPlan
    previous_ids = {node.node_id for node in (scene_before or ()) if node.node_id}
    previous_paths = {node.path for node in (scene_before or ())}
    generated_units = tuple(node.path for node in host.capture_body_scene_nodes()
        if node.node_type == 'unitConversion'
        and (node.node_id not in previous_ids if node.node_id
             else node.path not in previous_paths))
    host.name_body_unit_conversions(BodyAllSetPlan(generated_units))
    registration = (host.describe_character_registration(
        rig, source_character_channels(rig)) if defer_registration
        else RegisterBodyCharacter(host).apply(rig))
    finalize_body_character_sets(host, registration, rig_plan,
        segments=(tuple(part.name for part in build.fit_parts)
                  if part_result is not None else ()),
        scene_before=scene_before, fit_container=fit,
        create_sets=not defer_selection_sets,
        populate_all=not (defer_selection_sets or defer_all_set))
    return RegisteredBodyBuildResult(skeleton, rig, registration,
        segment_influences=(tuple(part.name for part in build.fit_parts)
                            if part_result is not None else ()),
        fit_part_hierarchy=part_result, inbetween_segments=inbetween_segments,
        ik_solver_mapping=solver_mapping)
