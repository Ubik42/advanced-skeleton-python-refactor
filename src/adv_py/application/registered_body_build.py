"""Build and register a complete Body character in one host transaction."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_part import rebase_plan_paths_after_parts
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
from .finger_mid_deform import BuildFingerMidDeform
from .fit_part import BuildFitPartHierarchy, FitPartHierarchyResult
from .fit_part_twist import (
    BuildFitPartTwistDrivers, PrepareFitPartTwistSources,
)
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
              ) -> RegisteredBodyBuildResult:
        if use_fit_part_hierarchy and not include_segment_influences:
            raise ValueError("通用 Fit Part 构建需要启用分段 Skin 影响")
        if not use_fit_part_hierarchy and fit_part_twist_sources:
            raise ValueError("扭转来源只能随通用 Fit Part 构建提供")
        preview = BuildOrientedBodySkeleton(self._host).plan(
            container_name, infer_missing_labels=infer_missing_labels)
        if not preview.ready:
            raise FitSkeletonValidationError(
                "角色构建预检失败，场景未修改：" + "；".join(preview.blockers))
        rotation_inputs = ()
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
                    and hip_selection.child_name != "Spine1"):
                raise FitSkeletonValidationError(
                    "有 Root Part 的 HipSwinger 目前只支持 Spine1 子关节")
            untwister_sources = frozenset(
                item.joint for item in fit_source.metadata
                if item.untwister and (item.inbetween_joints or 0) > 0)
            if inbetween_plan.guides:
                part_plan = plan_combined_part_hierarchy(
                    preview.build, inbetween_plan)
            if (hip_selection is not None and hip_selection.enabled
                    and hip_selection.root_inbetween_count
                    and not any(part.kind == "inbetween"
                                and part.start_body_name == "Root_M"
                                and part.end_body_name == "Spine1_M"
                                for part in part_plan.fit_parts)):
                raise FitSkeletonValidationError(
                    "Root 分段 HipSwinger 缺少 Root 至 Spine1 的 Part 链")
            twist_parts = tuple(part for part in part_plan.fit_parts
                                if part.kind == "twist")
            if fit_part_twist_sources is None:
                rotation_inputs = plan_standard_fit_part_rotation_inputs(
                    twist_parts)
                projections = plan_fit_part_twist_projections(rotation_inputs)
                preview_sources = tuple(item.source() for item in projections)
            else:
                preview_sources = fit_part_twist_sources
            plan_fit_part_twist(twist_parts, preview_sources)
        else:
            hip_selection = plan_hip_swing_fit_selection(
                self._host.capture_fit_orientation(container_name),
                allow_missing_child=(axial_description is not None
                                     and axial_description
                                     != BodyAxialDescription()))
        with self._host.transaction("构建并登记完整 Body 角色"):
            joined = _JoinedTransactionHost(self._host)
            skeleton = BuildOrientedBodySkeleton(joined).apply(
                container_name, infer_missing_labels=infer_missing_labels)
            rig = BuildBodyCharacterRig(joined).apply(container_name,
                include_torso=True, include_spine_ik=True,
                include_control_spaces=True, axial_description=axial_description,
                include_head_aim=include_head_aim)
            fit_part_hierarchy = None
            inbetween_segments = ()
            solver_mapping = None
            inbetween_untwisters = ()
            hip_swing_reverse = None
            if use_fit_part_hierarchy:
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
                BuildFitPartTwistDrivers(joined).apply(
                    twist_parts, active_twist_sources)
                BuildFitPartScaleDrivers(joined).apply(
                    part_plan.fit_parts)
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
                                or hip_selection.child_name != "Spine1"
                                or root_bindings[0].parts[-1].end_body_name
                                != "Spine1_M"
                                or len(root_bindings[0].parts)
                                != hip_selection.root_inbetween_count):
                            raise ValueError(
                                "HipSwingReverse 需要 Root 至 Spine1 的完整 Part 链")
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
                rig = replace(rig, plan=rebased_plan, body=driven_body)
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
            if inbetween_segments or hip_swing_reverse is not None:
                registration = RegisterInbetweenControls(joined).apply(
                    registration, inbetween_segments,
                    hip_swing=hip_swing_reverse)
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
        return RegisteredBodyBuildResult(
            skeleton, rig, registration, tuple(segments),
            fit_part_hierarchy, inbetween_segments,
            inbetween_untwisters, hip_swing_reverse,
            solver_mapping)
