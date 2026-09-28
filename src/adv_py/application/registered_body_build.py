"""Build and register a complete Body character in one host transaction."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_part import rebase_plan_paths_after_parts
from adv_py.core.fit_bendy import plan_fit_bendy_chains
from adv_py.core.fit_inbetween_untwister import InbetweenUnTwisterPlan
from adv_py.core.fit_inbetween_hip_swing import (
    HipSwingReversePlan, plan_hip_swing_fit_selection,
)
from adv_py.core.fit_hip_swing_no_parts import HipSwingNoPartsPlan
from adv_py.core.fit_part_twist import (
    FitPartTwistSource, plan_fit_part_twist,
    plan_fit_part_twist_projections,
    plan_standard_fit_part_rotation_inputs,
)
from adv_py.core.body_torso import audit_body_torso
from adv_py.core.body_limb_controls import audit_body_limb_fk_controls
from adv_py.core.body_leg_controls import terminal_toes_end_control_enabled
from adv_py.core.body_hand_controls import audit_body_hand_fk_controls
from adv_py.core.body_arm_ik import audit_body_arm_ik
from adv_py.core.body_leg_ik import audit_body_leg_ik
from adv_py.core.body_leg_foot import audit_body_leg_foot
from adv_py.core.body_arm_mechanisms import audit_body_arm_mechanisms
from adv_py.core.body_leg_mechanisms import audit_body_leg_mechanisms
from adv_py.core.fit_inbetween_ik_rebase import rebase_inbetween_ik_reference

from .axial_part_deform import BuildAxialPartDeform
from .body_character_rig import (BuildBodyCharacterRig,
                                 BodyCharacterRigBuildPlan,
                                 BodyCharacterRigBuildResult)
from .body_rig_validation import body_bind_pose_matches
from .character_registry import RegisterBodyCharacter
from .body_selection_sets import BuildBodySelectionSets
from .body_build_pose import GoToBodyBuildPose
from .finger_mid_deform import BuildFingerMidDeform
from .fit_part import BuildFitPartHierarchy, FitPartHierarchyResult
from .fit_bendy import (BuildFitBendyDeform, BuildFitBendyGuides,
                        plan_fit_bendy_follow)
from .fit_bendy_registration import RegisterBendyControls
from .fit_part_twist import (
    BuildFitPartTwistDrivers, PrepareFitPartTwistSources,
)
from .fit_part_registration import RegisterFitPartChannels
from .fit_part_scale import BuildFitPartScaleDrivers
from .fit_inbetween import PrepareFitInbetween
from .fit_inbetween_body import plan_combined_part_hierarchy
from .fit_inbetween_limb_mapping import (
    InbetweenFkBinding, InbetweenLimbBinding,
    plan_inbetween_limb_bindings,
)
from .fit_inbetween_limb_segment import (
    BuildInbetweenLimbSegments, InbetweenLimbSegmentResult,
)
from .fit_inbetween_ik_solver_mapping import (
    InbetweenIkSolverMapping,
    rebase_character_rig_after_inbetween_ik,
)
from .fit_inbetween_fk_segment import (
    BuildInbetweenFkSegment, InbetweenFkSegmentResult,
)
from .fit_inbetween_registration import RegisterInbetweenControls
from .fit_inbetween_untwister import BuildInbetweenUnTwister
from .fit_inbetween_hip_swing import BuildHipSwingReverse
from .fit_hip_swing_no_parts import (
    BuildHipSwingNoParts, character_hip_swing_no_parts_topology,
)
from .limb_part_deform import BuildLimbPartDeform
from .oriented_body_skeleton import (BuildOrientedBodySkeleton,
    OrientedBodySkeletonBuildResult)


_DEFORMATION_SYSTEM_PATH = "|Group|DeformationSystem"


class _JoinedTransactionHost:
    """Forward host operations while the outer build owns the undo chunk."""

    def __init__(self, host):
        self._host = host

    def __getattr__(self, name):
        return getattr(self._host, name)

    @contextmanager
    def transaction(self, label):
        del label
        yield


def _independent_rig_twist_sources(
    plan: BodyCharacterRigBuildPlan,
) -> tuple[
    dict[str, str], dict[str, str],
    dict[str, tuple[str, str, str, str]],
]:
    """Read control or mechanism matrices outside the driven Part hierarchy."""
    controls = []
    if plan.torso is not None:
        controls.extend(plan.torso.torso.controls.controls)
    if plan.hand is not None:
        controls.extend(plan.hand.controls.controls)
    body_paths = {joint.path for joint in plan.arm.safety.body.joints}
    controls = [control for control in controls
                if control.driven_joint in body_paths]
    matrices = {
        control.driven_joint: (
            control.source_override_path or control.sub_control_path
            or control.control_path) + ".worldMatrix[0]"
        for control in controls
    }
    constraints = {control.driven_joint: control.constraint_name
                   for control in controls}
    blended_matrices: dict[str, tuple[str, str, str, str]] = {}
    spine = plan.torso.torso.spine if plan.torso is not None else None
    if spine is not None:
        blended_matrices[spine.body_joints[1]] = (
            spine.joints[1].path + ".worldMatrix[0]",
            spine.waist_output + ".worldMatrix[0]",
            spine.blend_plug, "AdvPy_SpineWaistOrient")
        blended_matrices[spine.body_joints[2]] = (
            spine.joints[2].path + ".worldMatrix[0]",
            spine.joints[5].path + ".worldMatrix[0]",
            spine.blend_plug, "AdvPy_SpineChestOrient")
    spline = plan.torso.torso.spline if plan.torso is not None else None
    if spline is not None:
        count = len(spline.body_joints)
        for index in range(1, count):
            blended_matrices[spline.body_joints[index]] = (
                spline.joints[index].path + ".worldMatrix[0]",
                spline.ik_outputs[index] + ".worldMatrix[0]",
                spline.settings + ".spineIkFk",
                f"AdvPy_SplineOrient{index}")
    for module in (plan.arm, plan.leg):
        for side in module.blend.sides:
            weight = module.blend.settings_path + "." + side.attribute
            for joint in side.joints:
                if joint.body_joint not in body_paths:
                    raise ValueError("Part Twist 机制来源不属于当前 Body："
                                     + joint.body_joint)
                if joint.body_joint in matrices or joint.body_joint in blended_matrices:
                    raise ValueError("Part Twist 混合来源重复："
                                     + joint.body_joint)
                blended_matrices[joint.body_joint] = (
                    joint.fk_driver + ".worldMatrix[0]",
                    joint.ik_driver + ".worldMatrix[0]",
                    weight, joint.constraint_name)
    # Spine controls remain in the FK list, but their Body joints are also
    # driven by spine IK. The mixed mechanism is the actual rotation source.
    for body in blended_matrices:
        matrices.pop(body, None)
        constraints.pop(body, None)
    return matrices, constraints, blended_matrices


def _with_inbetween_fk_sources(
    plan: BodyCharacterRigBuildPlan,
    segments: tuple[InbetweenLimbSegmentResult | InbetweenFkSegmentResult, ...],
) -> BodyCharacterRigBuildPlan:
    """Keep the stored rig plan aligned with FK constraints moved to FKX."""
    if not segments:
        return plan
    sources: dict[str, tuple[str, str]] = {}
    for segment in segments:
        rewire = segment.rewire
        name = rewire.start_fk_constraint_name
        if name in sources:
            raise ValueError("Inbetween FK 约束被多条段重复改接：" + name)
        anchor = segment.fk.anchor
        if rewire.start_fkx_name != anchor.fkx_name:
            raise ValueError("Inbetween FKX 计划与实际改接来源不一致："
                             + name)
        sources[name] = (rewire.start_fk_control_path,
                         anchor.fk_offset_path + "|" + anchor.fkx_name)
    matched: set[str] = set()

    def update(controls):
        specs = []
        for spec in controls.controls:
            source = sources.get(spec.constraint_name)
            if source is None:
                specs.append(spec)
                continue
            if spec.control_path != source[0]:
                raise ValueError("Inbetween FK 改接与控制计划不一致："
                                 + spec.constraint_name)
            specs.append(replace(spec, source_override_path=source[1]))
            matched.add(spec.constraint_name)
        return replace(controls, controls=tuple(specs))

    arm = replace(plan.arm,
                  fk_controls=update(plan.arm.fk_controls))
    leg = replace(plan.leg,
                  fk_controls=update(plan.leg.fk_controls))
    hand = (replace(plan.hand, controls=update(plan.hand.controls))
            if plan.hand is not None else None)
    torso = (replace(plan.torso, torso=replace(
        plan.torso.torso,
        controls=update(plan.torso.torso.controls)))
        if plan.torso is not None else None)
    if matched != set(sources):
        raise ValueError("Inbetween FK 改接缺少原控制计划："
                         + "、".join(sorted(set(sources) - matched)))
    return replace(plan, arm=arm, leg=leg, hand=hand, torso=torso)


@dataclass(frozen=True, slots=True)
class RegisteredBodyBuildResult:
    skeleton: OrientedBodySkeletonBuildResult
    rig: BodyCharacterRigBuildResult
    registration: CharacterRegistration
    segment_influences: tuple[str, ...] = ()
    fit_part_hierarchy: FitPartHierarchyResult | None = None
    inbetween_segments: tuple[
        InbetweenLimbSegmentResult | InbetweenFkSegmentResult, ...] = ()
    inbetween_untwisters: tuple[InbetweenUnTwisterPlan, ...] = ()
    hip_swing_reverse: HipSwingReversePlan | HipSwingNoPartsPlan | None = None
    ik_solver_mapping: InbetweenIkSolverMapping | None = None


class BuildRegisteredBodyCharacter:
    """Materialize Body, controls and registry as one undoable operation."""

    def __init__(self, host):
        self._host = host

    def apply(self, container_name: str = "FitSkeleton", *,
              axial_description=None, include_head_aim: bool = False,
              infer_missing_labels: bool = False,
              include_segment_influences: bool = False,
              use_fit_part_hierarchy: bool = False,
              fit_part_twist_sources: tuple[FitPartTwistSource, ...] | None = None,
              _hierarchy_prepared: bool = False,
              ) -> RegisteredBodyBuildResult:
        if use_fit_part_hierarchy and not include_segment_influences:
            raise ValueError("通用 Fit Part 构建需要启用分段 Skin 影响")
        if not use_fit_part_hierarchy and fit_part_twist_sources:
            raise ValueError("扭转来源只能随通用 Fit Part 构建提供")
        if not _hierarchy_prepared:
            hierarchy_collisions = tuple(
                path for name in ("Group", "DeformationSystem", "Geometry",
                                  "MotionSystem", "FKSystem", "IKSystem",
                                  "FKIKSystem", "TwistSystem",
                                  "BendSystem", "RootSystem",
                                  "RootFollowMain", "GlobalSystem",
                                  "GlobalFollowMain", "AimSystem",
                                  "ConstraintSystem", "DrivingSystem")
                for path in self._host.find_name_collisions(name))
            if hierarchy_collisions:
                raise FitSkeletonValidationError(
                    "角色系统层级名称已被占用："
                    + "、".join(hierarchy_collisions))
            with self._host.transaction("构建并登记完整 Body 角色"):
                joined = _JoinedTransactionHost(self._host)
                if joined.create_body_system_hierarchy() != _DEFORMATION_SYSTEM_PATH:
                    raise RuntimeError("Body 变形系统层级创建路径漂移")
                fit_path = joined.parent_fit_skeleton_under_group(container_name)
                return BuildRegisteredBodyCharacter(joined).apply(
                    fit_path, axial_description=axial_description,
                    include_head_aim=include_head_aim,
                    infer_missing_labels=infer_missing_labels,
                    include_segment_influences=include_segment_influences,
                    use_fit_part_hierarchy=use_fit_part_hierarchy,
                    fit_part_twist_sources=fit_part_twist_sources,
                    _hierarchy_prepared=True)
        preview = BuildOrientedBodySkeleton(self._host).plan(
            container_name, infer_missing_labels=infer_missing_labels,
            root_parent_path=_DEFORMATION_SYSTEM_PATH)
        if not preview.ready:
            raise FitSkeletonValidationError(
                "角色构建预检失败，场景未修改：" + "；".join(preview.blockers))
        if (preview.build.build_options.use_offset_parent_matrix
                and any(item.tweaker_control
                        for item in preview.build.symmetry.source.metadata)):
            raise FitSkeletonValidationError(
                "Fit tweakerControl 的 OPM 关节驱动尚未接入 Body 主构建")
        rotation_inputs = ()
        bendy_chains = ()
        untwister_sources: frozenset[str] = frozenset()
        hip_selection = None
        part_plan = preview.build
        if use_fit_part_hierarchy:
            fit_source, inbetween_plan = PrepareFitInbetween(self._host).plan(
                container_name)
            hip_selection = plan_hip_swing_fit_selection(
                fit_source,
                allow_missing_child=(axial_description is not None
                                     and axial_description
                                     != BodyAxialDescription()))
            if (hip_selection is not None and hip_selection.enabled
                    and hip_selection.root_inbetween_count
                    and (axial_description.spine[1]
                         if axial_description is not None
                         else "Spine1_M")
                    != hip_selection.child_name + "_M"):
                raise FitSkeletonValidationError(
                    "有 Root Part 的 HipSwinger 须标记脊柱首节")
            untwister_sources = frozenset(
                item.joint for item in fit_source.metadata
                if item.untwister and (item.inbetween_joints or 0) > 0)
            if inbetween_plan.guides:
                part_plan = plan_combined_part_hierarchy(
                    preview.build, inbetween_plan)
            terminal_untwister = any(
                part.kind == "inbetween"
                and part.source_joint in untwister_sources
                and part.start_body_name == f"Toes_{part.side.value}"
                and part.end_body_name == f"ToesEnd_{part.side.value}"
                for part in part_plan.fit_parts
            )
            terminal_control = terminal_toes_end_control_enabled(
                fit_source.metadata)
            if terminal_untwister and not terminal_control:
                raise FitSkeletonValidationError(
                    "Toes→ToesEnd UnTwister 需要末端 Fit ToesEnd 的 "
                    "control 属性，以创建 FK 控制器及 Offset"
                )
            if (hip_selection is not None and hip_selection.enabled
                    and hip_selection.root_inbetween_count
                    and not any(part.kind == "inbetween"
                                and part.start_body_name == "Root_M"
                                and part.end_body_name
                                == hip_selection.child_name + "_M"
                                for part in part_plan.fit_parts)):
                raise FitSkeletonValidationError(
                    "Root 分段 HipSwinger 缺少 Root 至脊柱首节的 Part 链")
            twist_parts = tuple(part for part in part_plan.fit_parts
                                if part.kind == "twist")
            bendy_chains = plan_fit_bendy_chains(
                twist_parts, fit_source.metadata, part_plan.specs)
            bendy_part_names = {name for chain in bendy_chains
                                for name in chain.part_names}
            ordinary_twist_parts = tuple(
                part for part in twist_parts
                if part.name not in bendy_part_names)
            if fit_part_twist_sources is not None:
                plan_fit_part_twist(ordinary_twist_parts,
                                    fit_part_twist_sources)
        else:
            hip_selection = plan_hip_swing_fit_selection(
                self._host.capture_fit_orientation(container_name),
                allow_missing_child=(axial_description is not None
                                     and axial_description
                                     != BodyAxialDescription()))
        if (hip_selection is not None and hip_selection.enabled
                and hip_selection.root_inbetween_count == 0
                and axial_description is not None
                and axial_description != BodyAxialDescription()
                and axial_description.spine[1]
                != hip_selection.child_name + "_M"):
            raise FitSkeletonValidationError(
                "无 Root Part 的自定义 HipSwinger 须标记脊柱首节")
        with self._host.transaction("构建并登记完整 Body 角色"):
            joined = _JoinedTransactionHost(self._host)
            skeleton = BuildOrientedBodySkeleton(joined).apply(
                container_name, infer_missing_labels=infer_missing_labels,
                root_parent_path=_DEFORMATION_SYSTEM_PATH)
            rig = BuildBodyCharacterRig(joined).apply(container_name,
                include_torso=True, include_spine_ik=True,
                include_control_spaces=True, axial_description=axial_description,
                include_head_aim=include_head_aim)
            if bendy_chains:
                follows = plan_fit_bendy_follow(bendy_chains, rig.plan)
                BuildFitBendyGuides(joined).apply(bendy_chains,
                                                  follows=follows)
            fit_part_hierarchy = None
            twist_steps = ()
            inbetween_segments = ()
            solver_mapping = None
            inbetween_untwisters = ()
            hip_swing_reverse = None
            if use_fit_part_hierarchy:
                (control_matrices, body_constraints,
                 blended_matrices) = (
                    _independent_rig_twist_sources(rig.plan))
                if fit_part_twist_sources is None:
                    rotation_inputs = plan_standard_fit_part_rotation_inputs(
                        ordinary_twist_parts,
                        independent_world_matrices=control_matrices,
                        independent_body_constraints=body_constraints,
                        blended_world_matrices=blended_matrices)
                    projections = plan_fit_part_twist_projections(
                        rotation_inputs)
                    plan_fit_part_twist(
                        ordinary_twist_parts,
                        tuple(item.source() for item in projections
                              if item.input.distribution_source))
                twist_sources = (
                    PrepareFitPartTwistSources(joined).apply(rotation_inputs)
                    if fit_part_twist_sources is None
                    else fit_part_twist_sources
                )
                fit_part_hierarchy = BuildFitPartHierarchy(joined).apply(
                    part_plan)
                final_paths = fit_part_hierarchy.final_paths
                active_twist_sources = tuple(replace(
                    source,
                    down_twist_plug=final_paths.remap_body_reference(
                        source.down_twist_plug),
                    up_twist_plug=(final_paths.remap_body_reference(
                        source.up_twist_plug) if source.up_twist_plug else None),
                ) for source in twist_sources)
                twist_steps = BuildFitPartTwistDrivers(joined).apply(
                    ordinary_twist_parts, active_twist_sources)
                BuildFitPartScaleDrivers(joined).apply(
                    part_plan.fit_parts)
                if bendy_chains:
                    BuildFitBendyDeform(joined).apply(bendy_chains)
                inbetween_parts = tuple(
                    part for part in part_plan.fit_parts
                    if part.kind == "inbetween")
                if inbetween_parts:
                    bindings = plan_inbetween_limb_bindings(
                        inbetween_parts, rig.plan,
                        final_paths=final_paths)
                    limb_bindings = tuple(
                        binding for binding in bindings
                        if isinstance(binding, InbetweenLimbBinding))
                    bulk = BuildInbetweenLimbSegments(joined).apply(
                        limb_bindings, rig.plan)
                    solver_mapping = bulk.solver_mapping
                    limb_results = iter(bulk.segments)
                    built_segments = []
                    for binding in bindings:
                        if isinstance(binding, InbetweenFkBinding):
                            # The Neck Body joint is reparented by the Part
                            # hierarchy; limb FK mechanism paths stay fixed.
                            neck_driver = final_paths.remap_body_reference(
                                binding.start_fk_driver_path)
                            built_segments.append(
                                BuildInbetweenFkSegment(joined).apply(
                                    binding.parts,
                                    fk_offset_path=binding.fk_offset_path,
                                    fk_control_path=binding.fk_control_path,
                                    fk_system_path=binding.fk_system_path,
                                    start_fk_driver_path=neck_driver,
                                    start_fk_constraint_name=(
                                        binding.start_fk_constraint_name),
                                    downstream_fk_offset_path=(
                                        binding.downstream_fk_offset_path),
                                    rotate_order=binding.rotate_order,
                                    part_control_radius=(
                                        binding.part_control_radius),
                                ))
                            continue
                        built_segments.append(next(limb_results))
                    inbetween_segments = tuple(built_segments)
                    if any(binding.parts[0].source_joint
                           in untwister_sources
                           and (binding.end_fk_control_path is None
                                or binding.downstream_fk_offset_path is None)
                           for binding in bindings):
                        raise ValueError(
                            "末端 Inbetween UnTwister 缺少下游 FK 旋转来源")
                    inbetween_untwisters = tuple(
                        BuildInbetweenUnTwister(joined).apply(
                            binding.parts,
                            tuple(item.constraint_name
                                  for item in segment.body.parts),
                            end_fk_control_path=(
                                binding.end_fk_control_path),
                            end_fk_offset_path=(
                                binding.downstream_fk_offset_path),
                        )
                        for binding, segment in zip(bindings,
                                                    inbetween_segments)
                        if binding.parts[0].source_joint
                        in untwister_sources
                    )
                    if (hip_selection is not None
                            and hip_selection.enabled
                            and hip_selection.root_inbetween_count):
                        root_bindings = [binding for binding in bindings
                                         if binding.parts[0].start_body_name
                                         == "Root_M"]
                        if (len(root_bindings) != 1
                                or root_bindings[0].parts[-1].end_body_name
                                != hip_selection.child_name + "_M"
                                or len(root_bindings[0].parts)
                                != hip_selection.root_inbetween_count):
                            raise ValueError(
                                "HipSwingReverse 需要 Root 至脊柱首节的完整 Part 链")
                        root_binding = root_bindings[0]
                        hip_swing_reverse = BuildHipSwingReverse(joined).apply(
                            root_binding.parts,
                            start_fk_offset_path=(
                                root_binding.fk_offset_path),
                            start_fk_control_path=(
                                root_binding.fk_control_path),
                            end_body_path=final_paths.remap_body_reference(
                                root_binding.parts[-1].end_body),
                            radius=root_binding.part_control_radius * 3.0,
                            root_profile=next(
                                spec.deform_profile
                                for spec in part_plan.specs
                                if spec.name == "Root_M"),
                        )
                active_part_rig_plan = rebase_plan_paths_after_parts(
                    rig.plan, final_paths)
                driven_body = joined.capture_body_skeleton(
                    skeleton.snapshot.root)
                if not body_bind_pose_matches(
                        fit_part_hierarchy.body, driven_body):
                    raise RuntimeError("Fit Part 驱动改变了 Body 绑定姿态")
                rebased_plan = _with_inbetween_fk_sources(
                    active_part_rig_plan,
                    inbetween_segments)
                if solver_mapping is not None:
                    rebased_plan = rebase_character_rig_after_inbetween_ik(
                        rebased_plan, solver_mapping)
                # Part creation reparents Body joints.  Keep every result
                # returned by this build on the same final DAG as the
                # registration and Skin inputs, even without Inbetween parts.
                skeleton = replace(
                    skeleton,
                    snapshot=driven_body,
                    orientation_changes=rebase_plan_paths_after_parts(
                        skeleton.orientation_changes, final_paths),
                )
                rig = replace(
                    rig,
                    plan=rebased_plan,
                    body=driven_body,
                    arm=replace(
                        rebase_plan_paths_after_parts(rig.arm, final_paths),
                        plan=rebased_plan.arm, body=driven_body),
                    leg=replace(
                        rebase_plan_paths_after_parts(rig.leg, final_paths),
                        plan=rebased_plan.leg, body=driven_body),
                    hand=(replace(
                        rebase_plan_paths_after_parts(rig.hand, final_paths),
                        plan=rebased_plan.hand, body=driven_body)
                        if rig.hand is not None and rebased_plan.hand is not None
                        else None),
                    torso=(rebase_plan_paths_after_parts(rig.torso, final_paths)
                           if rig.torso is not None else None),
                )
                if inbetween_segments:
                    arm_fk = joined.capture_body_arm_fk_controls(
                        rig.plan.arm.fk_controls)
                    leg_fk = joined.capture_body_leg_fk_controls(
                        rig.plan.leg.fk_controls)
                    fk_issues = tuple(audit_body_limb_fk_controls(
                        rig.plan.arm.fk_controls, arm_fk,
                        limb_label="Arm")) + tuple(
                        audit_body_limb_fk_controls(
                            rig.plan.leg.fk_controls, leg_fk,
                            limb_label="Leg"))
                    if fk_issues:
                        raise RuntimeError(
                            "Inbetween 改接后四肢 FK 复检失败："
                            + "；".join(issue.message
                                       for issue in fk_issues))
                    solvers = tuple(
                        request.plan for request in
                        solver_mapping.requests) if solver_mapping else ()
                    if solvers:
                        arm_mechanisms = joined.capture_body_arm_mechanisms(
                            rig.plan.arm.mechanisms)
                        leg_mechanisms = joined.capture_body_leg_mechanisms(
                            rig.plan.leg.mechanisms)
                        arm_ik = joined.capture_body_arm_ik(
                            rig.plan.arm.ik)
                        leg_ik = joined.capture_body_leg_ik(
                            rig.plan.leg.ik)
                        leg_foot = joined.capture_body_leg_foot(
                            rig.plan.leg.foot)
                        ik_issues = (
                            *audit_body_arm_mechanisms(
                                rig.plan.arm.mechanisms, arm_mechanisms,
                                check_initial_pose=False),
                            *audit_body_leg_mechanisms(
                                rig.plan.leg.mechanisms, leg_mechanisms,
                                check_initial_pose=False),
                            *audit_body_arm_ik(
                                rig.plan.arm.ik, arm_ik,
                                check_initial_pose=False),
                            *audit_body_leg_ik(
                                rig.plan.leg.ik, leg_ik,
                                check_initial_pose=False,
                                expected_handle_parent_by_side={
                                    side.side:
                                    side.final_handle_parent_path
                                    for side in rig.plan.leg.foot.sides},
                                expected_ankle_source_by_side={
                                    side.side:
                                    side.ankle_orientation_source_path
                                    for side in rig.plan.leg.foot.sides}),
                            *audit_body_leg_foot(
                                rig.plan.leg.foot, leg_foot,
                                check_initial_pose=False),
                        )
                        if ik_issues:
                            raise RuntimeError(
                                "Inbetween 求解链复检失败："
                                + "；".join(issue.message
                                           for issue in ik_issues))
                        rig = replace(
                            rig,
                            arm=replace(
                                rebase_inbetween_ik_reference(
                                    rig.arm, solvers),
                                plan=rig.plan.arm,
                                mechanisms=arm_mechanisms, ik=arm_ik),
                            leg=replace(
                                rebase_inbetween_ik_reference(
                                    rig.leg, solvers),
                                plan=rig.plan.leg,
                                mechanisms=leg_mechanisms, ik=leg_ik,
                                foot=leg_foot),
                        )
                    rig = replace(rig,
                        arm=replace(rig.arm, plan=rig.plan.arm,
                                    fk_controls=arm_fk, body=driven_body),
                        leg=replace(rig.leg, plan=rig.plan.leg,
                                    fk_controls=leg_fk, body=driven_body))
                    if rig.plan.hand is not None and rig.hand is not None:
                        hand_fk = joined.capture_body_hand_fk_controls(
                            rig.plan.hand.controls)
                        hand_issues = audit_body_hand_fk_controls(
                            rig.plan.hand.controls, hand_fk)
                        if hand_issues:
                            raise RuntimeError(
                                "Inbetween 改接后 Hand FK 复检失败："
                                + "；".join(issue.message
                                           for issue in hand_issues))
                        rig = replace(rig, hand=replace(
                            rig.hand, plan=rig.plan.hand,
                            snapshot=hand_fk, body=driven_body))
                    if rig.plan.torso is not None:
                        torso_snapshot = joined.capture_body_torso(
                            rig.plan.torso.torso)
                        torso_issues = audit_body_torso(
                            rig.plan.torso.torso, torso_snapshot)
                        if torso_issues:
                            raise RuntimeError(
                                "Inbetween 改接后 Torso 复检失败："
                                + "；".join(torso_issues))
                        rig = replace(rig, torso=torso_snapshot)
            if (hip_selection is not None and hip_selection.enabled
                    and hip_selection.root_inbetween_count == 0):
                topology = character_hip_swing_no_parts_topology(
                    rig.plan, child_name=hip_selection.child_name)
                torso_plan = rig.plan.torso.torso
                root_control = next(
                    control for control in torso_plan.controls.controls
                    if control.control_path == topology.fk_root_path)
                hip_swing_reverse = BuildHipSwingNoParts(joined).apply(
                    hip_selection, topology, radius=root_control.radius,
                    root_profile=next(
                        spec.deform_profile for spec in part_plan.specs
                        if spec.name == "Root_M"),
                    use_offset_parent_matrix=(
                        torso_plan.use_offset_parent_matrix),
                )
                leg_lock = replace(
                    torso_plan.leg_lock,
                    compensation_source=(
                        hip_swing_reverse.fk_weight_blend_name
                        + ".outputMatrix"))
                torso_plan = replace(torso_plan, leg_lock=leg_lock)
                rig_plan = replace(
                    rig.plan,
                    torso=replace(rig.plan.torso, torso=torso_plan))
                torso_snapshot = joined.capture_body_torso(torso_plan)
                torso_issues = audit_body_torso(torso_plan, torso_snapshot)
                if torso_issues:
                    raise RuntimeError(
                        "无分段 HipSwinger 接线后 Torso 复检失败："
                        + "；".join(torso_issues))
                rig = replace(rig, plan=rig_plan, torso=torso_snapshot)
            registration = RegisterBodyCharacter(joined).apply(rig)
            if fit_part_hierarchy is not None and twist_steps:
                registration = RegisterFitPartChannels(joined).apply(
                    registration, twist_steps,
                    fit_part_hierarchy.final_paths)
            if inbetween_segments or hip_swing_reverse is not None:
                registration = RegisterInbetweenControls(joined).apply(
                    registration, inbetween_segments,
                    hip_swing=hip_swing_reverse)
            if bendy_chains:
                registration = RegisterBendyControls(joined).apply(
                    registration, bendy_chains)
            if len(registration.body) != len(skeleton.snapshot.joints):
                raise RuntimeError("登记骨架数量与本次构建结果不一致")
            segments: list[str] = []
            if fit_part_hierarchy is not None:
                segments.extend(path for _, path in
                                fit_part_hierarchy.final_paths.part_paths)
            elif include_segment_influences:
                # The five-finger and described axial helpers are optional Body
                # branches; the limb segments exist on every supported Body.
                body_names = {item.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                              for item in registration.body}
                axial = axial_description or BodyAxialDescription()
                if set(axial.spine + axial.neck) <= body_names:
                    segments.extend(spec.path for spec in
                        BuildAxialPartDeform(joined).apply(
                            axial_description=axial))
                original_fingers = {f"{digit}Finger{index}_{side}"
                                    for side in ("R", "L")
                                    for digit in ("Thumb", "Index", "Middle", "Ring", "Pinky")
                                    for index in (2, 3)}
                canonical_fingers = {f"{digit}{index}_{side}"
                                     for side in ("R", "L")
                                     for digit in ("Thumb", "Index", "Middle", "Ring", "Pinky")
                                     for index in (2, 3)}
                if (original_fingers <= body_names
                        or canonical_fingers <= body_names):
                    segments.extend(spec.path for spec in
                        BuildFingerMidDeform(joined).apply())
                for spec in BuildLimbPartDeform(joined).apply():
                    segments.extend((spec.part1, spec.part2))
            registered_controls = {channel.node
                                   for channel in registration.channels}
            fk_control_specs = (
                rig.plan.arm.fk_controls.controls
                + rig.plan.leg.fk_controls.controls
                + (rig.plan.hand.controls.controls
                   if rig.plan.hand is not None else ())
                + (rig.plan.torso.torso.controls.controls
                   if rig.plan.torso is not None else ()))
            locked_selection_extras = tuple(
                spec.extra_path or spec.control_path
                for spec in fk_control_specs
                if spec.control_path not in registered_controls
                and spec.control_path not in rig.plan.no_control_paths)
            BuildBodySelectionSets(joined).apply(
                registration, tuple(segments),
                extras=tuple(extra for chain in bendy_chains
                             for extra in chain.micro_extra_names)
                + locked_selection_extras)
            if joined.has_body_build_pose_overrides():
                GoToBodyBuildPose(joined).apply()
            joined.finalize_fit_skeleton_visibility(container_name)
            hierarchy = joined.capture_body_system_hierarchy(
                skeleton.snapshot.root, container_name)
            if hierarchy != (
                ("|Group", None, "transform"),
                (container_name, "|Group", "transform"),
                (_DEFORMATION_SYSTEM_PATH, "|Group", "transform"),
                ("|Group|Geometry", "|Group", "transform"),
                ("|Group|MotionSystem", "|Group", "transform"),
                ("|Group|MotionSystem|FKSystem",
                 "|Group|MotionSystem", "transform"),
                ("|Group|MotionSystem|IKSystem",
                 "|Group|MotionSystem", "transform"),
                ("|Group|MotionSystem|FKIKSystem",
                 "|Group|MotionSystem", "transform"),
                ("|Group|MotionSystem|TwistSystem",
                 "|Group|MotionSystem", "transform"),
                ("|Group|MotionSystem|BendSystem",
                 "|Group|MotionSystem", "transform"),
                ("|Group|MotionSystem|RootSystem",
                 "|Group|MotionSystem", "transform"),
                ("|Group|MotionSystem|RootSystem|RootFollowMain",
                 "|Group|MotionSystem|RootSystem", "transform"),
                ("|Group|MotionSystem|GlobalSystem",
                 "|Group|MotionSystem", "transform"),
                ("|Group|MotionSystem|GlobalSystem|GlobalFollowMain",
                 "|Group|MotionSystem|GlobalSystem", "transform"),
                ("|Group|MotionSystem|AimSystem",
                 "|Group|MotionSystem", "transform"),
                ("|Group|MotionSystem|ConstraintSystem",
                 "|Group|MotionSystem", "transform"),
                ("|Group|MotionSystem|DrivingSystem",
                 "|Group|MotionSystem", "transform"),
                (skeleton.snapshot.root, _DEFORMATION_SYSTEM_PATH, "joint"),
            ):
                raise RuntimeError("角色主构建结束时 Body 变形系统层级不一致")
        return RegisteredBodyBuildResult(
            skeleton, rig, registration, tuple(segments),
            fit_part_hierarchy, inbetween_segments,
            inbetween_untwisters, hip_swing_reverse,
            solver_mapping)
