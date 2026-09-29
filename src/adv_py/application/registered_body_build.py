"""Build and register a complete Body character in one host transaction."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import re

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_orientation import (
    FitOrientationRequest, select_fit_orientation_child,
)
from adv_py.core.fit_part import (
    rebase_plan_paths_after_parts, semantic_body_snapshot_after_parts,
)
from adv_py.core.fit_tweaker import plan_fit_tweakers
from adv_py.core.fit_bendy import (
    plan_fit_bendy_chains, plan_fit_bendy_fk_scales,
)
from adv_py.core.fit_inbetween_untwister import InbetweenUnTwisterPlan
from adv_py.core.fit_inbetween_hip_swing import (
    HipSwingReversePlan, plan_hip_swing_fit_selection,
)
from adv_py.core.fit_hip_swing_no_parts import HipSwingNoPartsPlan
from adv_py.core.fit_part_twist import (
    FitPartTwistSource, plan_fit_part_twist,
    plan_generic_fit_part_twist_rewires,
    plan_fit_part_twist_projections,
    plan_standard_fit_part_rotation_inputs,
)
from adv_py.core.body_torso import audit_body_torso
from adv_py.core.body_limb_controls import audit_body_limb_fk_controls
from adv_py.core.body_leg_controls import terminal_toes_end_control_enabled
from adv_py.core.body_leg_blend import audit_body_leg_blend
from adv_py.core.body_hand_controls import audit_body_hand_fk_controls
from adv_py.core.body_arm_ik import audit_body_arm_ik
from adv_py.core.body_leg_ik import audit_body_leg_ik
from adv_py.core.body_leg_foot import audit_body_leg_foot
from adv_py.core.body_arm_mechanisms import audit_body_arm_mechanisms
from adv_py.core.body_leg_mechanisms import audit_body_leg_mechanisms
from adv_py.core.fit_inbetween_ik_rebase import rebase_inbetween_ik_reference
from adv_py.core.body_fit_advanced_constraint import plan_body_fit_advanced_constraints
from adv_py.core.body_fit_follow import plan_body_fit_follow
from adv_py.core.body_fit_named_follow import plan_body_fit_named_follow
from adv_py.core.body_fit_follow_spaces import plan_body_fit_follow_spaces
from adv_py.core.body_fit_ik_follow import plan_body_fit_ik_follow
from adv_py.core.body_fit_aim_at import plan_body_fit_aim_at
from adv_py.core.body_fit_geo_attach import plan_body_fit_geo_attach
from adv_py.core.body_fit_proximity_pin import plan_body_fit_proximity_pin
from adv_py.core.body_fit_wheel import BodyFitWheelSpec, plan_body_fit_wheels
from adv_py.core.body_fit_curve_guide import (
    BodyFitCurveGuideBuilt, plan_body_fit_curve_guides,
)
from adv_py.core.body_generic_fk import (
    GenericFkFeaturePolicy, plan_body_generic_fk,
)
from adv_py.core.body_fk_channel_locks import BodyFkChannelLockSpec
from adv_py.core.body_fk_global import plan_body_fk_global, audit_body_fk_global
from adv_py.core.body_fit_aim import plan_body_fit_aim
from adv_py.core.body_build_options import BodyBuildOptions
from adv_py.core.fit_metadata import FitJointField
from adv_py.core.body_direct_fk_scale import plan_body_direct_fk_scales
from adv_py.core.body_fk_scale_compensation import plan_body_fk_scale_compensation
from adv_py.core.body_center_between_feet import plan_body_center_between_feet
from adv_py.core.body_fit_dependency import validate_fit_control_dependencies
from adv_py.core.body_system_hierarchy import (
    BODY_SYSTEM_RESERVED_NAMES, expected_body_system_hierarchy,
)

from .axial_part_deform import BuildAxialPartDeform
from .body_character_rig import (BuildBodyCharacterRig,
                                 BodyCharacterRigBuildPlan,
                                 BodyCharacterRigBuildResult)
from .body_fk_scale_compensation import BuildBodyFkScaleCompensation
from .body_rig_validation import body_bind_pose_matches
from adv_py.core.body_skeleton import (
    body_skeleton_unchanged, oriented_body_provenance,
    plan_body_non_deform_markers,
)
from .character_registry import RegisterBodyCharacter
from .body_selection_sets import (
    finalize_body_character_sets,
)
from .finger_mid_deform import BuildFingerMidDeform
from .fit_part import BuildFitPartHierarchy, FitPartHierarchyResult
from .fit_bendy import (BuildFitBendyDeform, BuildFitBendyFkScales,
                        BuildFitBendyGuides,
                        plan_fit_bendy_follow, split_fit_bendy_chains)
from .fit_bendy_registration import RegisterBendyControls
from .fit_part_twist import (
    AttachGenericFitPartTwistSources, BuildFitPartTwistDrivers,
    PrepareFitPartTwistSources,
)
from .fit_part_registration import RegisterFitPartChannels
from .fit_tweaker import BuildFitTweakers
from .fit_tweaker_registration import RegisterFitTweakers
from .body_fit_advanced_constraint import (
    BuildFitAdvancedConstraints, RegisterFitAdvancedConstraints,
)
from .body_fit_follow import BuildFitFollow, RegisterFitFollow
from .body_fit_named_follow import BuildFitNamedFollow, RegisterFitNamedFollow
from .body_fit_follow_spaces import BuildFitFollowSpaces, RegisterFitFollowSpaces
from .body_fit_ik_follow import BuildFitIkFollow, RegisterFitIkFollow
from .body_fit_aim_at import BuildFitAimAt, RegisterFitAimAt
from .body_fit_geo_attach import BuildFitGeoAttach, RegisterFitGeoAttach
from .body_fit_proximity_pin import (
    BuildFitProximityPin, RegisterFitProximityPin,
)
from .body_center_between_feet import (
    BuildCenterBetweenFeet, RegisterCenterBetweenFeet,
)
from .fit_wheel_registration import RegisterFitWheels
from .fit_curve_guide_registration import RegisterFitCurveGuides
from .generic_fk_registration import RegisterGenericFk
from .fit_part_scale import BuildFitPartScaleDrivers
from .fit_inbetween import PrepareFitInbetween
from .fit_orientation_auto import OrientFitJoints
from .fit_inbetween_body import plan_combined_part_hierarchy
from .fit_inbetween_limb_mapping import (
    InbetweenFkBinding, InbetweenLimbBinding,
    plan_generic_inbetween_fk_bindings, plan_inbetween_limb_bindings,
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


class _PartAwareRigHost:
    """Plan controls on final Body paths while hiding inserted Part edges."""

    def __init__(self, host, paths):
        self._host = host
        self._paths = paths

    def __getattr__(self, name):
        return getattr(self._host, name)

    def capture_physical_body_skeleton(self, root_name):
        return self._host.capture_body_skeleton(root_name)

    def capture_body_skeleton(self, root_name):
        return semantic_body_snapshot_after_parts(
            self.capture_physical_body_skeleton(root_name), self._paths)


def _independent_rig_twist_sources(
    plan: BodyCharacterRigBuildPlan,
) -> tuple[
    dict[str, str], dict[str, str],
    dict[str, tuple[str, str, str, str]],
    dict[str, str],
]:
    """Read control or mechanism matrices outside the driven Part hierarchy."""
    controls = []
    controls.extend(plan.arm.fk_controls.controls)
    controls.extend(plan.leg.fk_controls.controls)
    if plan.torso is not None:
        controls.extend(plan.torso.torso.controls.controls)
    if plan.hand is not None:
        controls.extend(plan.hand.controls.controls)
    body_paths = {joint.path for joint in plan.arm.safety.body.joints}
    controls = [control for control in controls
                if control.driven_joint in body_paths]
    if len({control.driven_joint for control in controls}) != len(controls):
        raise ValueError("Part Twist 同一 Body 关节存在多个 FK 控制来源")
    root_child_offsets = {
        control.driven_joint: control.offset_path + ".worldInverseMatrix[0]"
        for control in (plan.torso.torso.controls.controls
                        if plan.torso is not None else ())
        if control.driven_joint.rsplit("|", 1)[0].endswith("|Root_M")
    }
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
                if joint.body_joint in blended_matrices:
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
    return matrices, constraints, blended_matrices, root_child_offsets


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


def _with_wheel_fk_sources(
    plan: BodyCharacterRigBuildPlan,
    wheels: tuple[BodyFitWheelSpec, ...],
) -> BodyCharacterRigBuildPlan:
    sources = {
        wheel.control.constraint_name: (
            wheel.control.control_path,
            (wheel.control.sub_control_path
             or wheel.control.control_path)
            + "|AdvPy_WheelFKX"
            + wheel.control.control_name.removeprefix("AdvPy_"))
        for wheel in wheels if wheel.control.source_override_path is None
    }
    if not sources:
        return plan
    matched: set[str] = set()

    def update(controls):
        specs = []
        for spec in controls.controls:
            source = sources.get(spec.constraint_name)
            if source is None:
                specs.append(spec)
                continue
            if spec.control_path != source[0]:
                raise ValueError("Wheel FK 约束来源与计划不一致："
                                 + spec.constraint_name)
            specs.append(replace(spec, source_override_path=source[1]))
            matched.add(spec.constraint_name)
        return replace(controls, controls=tuple(specs))

    arm = replace(plan.arm, fk_controls=update(plan.arm.fk_controls))
    leg = replace(plan.leg, fk_controls=update(plan.leg.fk_controls))
    hand = (replace(plan.hand, controls=update(plan.hand.controls))
            if plan.hand is not None else None)
    torso = (replace(plan.torso, torso=replace(
        plan.torso.torso, controls=update(plan.torso.torso.controls)))
        if plan.torso is not None else None)
    if matched != set(sources):
        raise ValueError("Wheel FK 改接缺少原控制计划："
                         + "、".join(sorted(set(sources) - matched)))
    return replace(plan, arm=arm, leg=leg, hand=hand, torso=torso)


def preflight_registered_fit_parts(
    host, container_name: str, *,
    include_segment_influences: bool,
    use_fit_part_hierarchy: bool,
    fit_part_twist_sources: tuple[FitPartTwistSource, ...] | None = None,
) -> None:
    """Reject an incomplete Fit Part build before any scene hierarchy is made."""
    if use_fit_part_hierarchy and not include_segment_influences:
        raise ValueError("通用 Fit Part 构建需要启用分段 Skin 影响")
    if not use_fit_part_hierarchy and fit_part_twist_sources:
        raise ValueError("扭转来源只能随通用 Fit Part 构建提供")
    if use_fit_part_hierarchy:
        PrepareFitInbetween(host).plan(container_name)
        return
    source = host.capture_fit_orientation(container_name)
    omitted = tuple(item.joint for item in source.metadata
                    if (item.twist_joints or 0) > 0
                    or (item.inbetween_joints or 0) > 0)
    if omitted:
        raise FitSkeletonValidationError(
            "Fit 已标记 Twist／Inbetween，不能在关闭 Fit 分段时构建："
            + "、".join(omitted))


def _refresh_fit_orientations_before_body(host, container_name: str) -> None:
    """Run MEL's pre-build Fit aim pass before copying Body joint frames."""
    snapshot = host.capture_fit_orientation(container_name)
    targets = tuple(
        node.path for node in snapshot.hierarchy.joints
        if select_fit_orientation_child(snapshot, node.path) is not None
    )
    if targets:
        editor = OrientFitJoints(host)
        plan = editor.plan(FitOrientationRequest(targets), container_name)
        if plan.changes or plan.terminal_resets:
            editor.apply_plan_in_transaction(plan)


def _preflight_centered_root_spine(host, hierarchy) -> None:
    """Match the Root spline-IK center check in asBuildAdvancedSkeleton."""
    nodes = {node.path: node for node in hierarchy.joints}
    roots = [node for node in hierarchy.joints
             if node.dag_parent == hierarchy.container]
    if len(roots) != 1:
        return
    root = roots[0]
    root_label = host.read_joint_label(root.path)
    if root_label is None or not root_label.text.startswith("Root"):
        return
    chest = [node for node in hierarchy.joints
             if node.path.startswith(root.path + "|")
             and (label := host.read_joint_label(node.path)) is not None
             and "Chest" in label.text]
    if len(chest) != 1:
        return
    chain = []
    current = chest[0]
    while current.path != root.path:
        chain.append(current)
        if current.dag_parent not in nodes:
            return
        current = nodes[current.dag_parent]
    chain.append(root)
    maximum_y = max((node.world_position[1] for node in hierarchy.joints),
                    default=0.0)
    scale = max(0.01, maximum_y / 17.176163) if maximum_y > 0 else 1.0
    tolerance = 0.01 * scale
    off_center = [node.path for node in chain
                  if abs(node.world_position[0]) > tolerance]
    if off_center:
        raise FitSkeletonValidationError(
            "Root→Chest 脊柱 IK 链关节不在中线：" + "、".join(off_center)
        )


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
    selection_extras: tuple[str, ...] = ()
    curve_guides: tuple[BodyFitCurveGuideBuilt, ...] = ()
    wheels: tuple[BodyFitWheelSpec, ...] = ()


class BuildRegisteredBodyCharacter:
    """Materialize Body, controls and registry as one undoable operation."""

    def __init__(self, host):
        self._host = host

    def apply(self, container_name: str = "FitSkeleton", *,
              axial_description=None, include_head_aim: bool = False,
              infer_missing_labels: bool = False,
              include_segment_influences: bool = True,
              use_fit_part_hierarchy: bool = True,
              fit_part_twist_sources: tuple[FitPartTwistSource, ...] | None = None,
              _hierarchy_prepared: bool = False,
              _scene_before=None,
              _include_dynamic: bool = True,
              _defer_selection_sets: bool = False,
              _defer_all_set: bool = False,
              _retain_non_deform_markers: bool = False,
              _generic_fk_policy: GenericFkFeaturePolicy | None = None,
              ) -> RegisteredBodyBuildResult:
        if (_generic_fk_policy is not None and
                not isinstance(_generic_fk_policy, GenericFkFeaturePolicy)):
            raise ValueError("通用 FK 重建图策略无效")
        if _scene_before is None:
            capture_nodes = getattr(self._host,
                                    "capture_body_scene_nodes", None)
            if capture_nodes is not None:
                _scene_before = capture_nodes()
        if use_fit_part_hierarchy and not include_segment_influences:
            raise ValueError("通用 Fit Part 构建需要启用分段 Skin 影响")
        if not use_fit_part_hierarchy and fit_part_twist_sources:
            raise ValueError("扭转来源只能随通用 Fit Part 构建提供")
        if not _hierarchy_prepared:
            hierarchy_collisions = tuple(
                path for name in BODY_SYSTEM_RESERVED_NAMES
                for path in self._host.find_name_collisions(name))
            if hierarchy_collisions:
                raise FitSkeletonValidationError(
                    "角色系统层级名称已被占用："
                    + "、".join(hierarchy_collisions))
            with self._host.transaction("构建并登记完整 Body 角色"):
                joined = _JoinedTransactionHost(self._host)
                original_up_axis = joined.scene_up_axis().value
                try:
                    joined.collapse_fit_generated_transforms(container_name)
                    joined.prepare_fit_root(container_name)
                    joined.normalize_fit_joint_names(container_name)
                    joined.normalize_fit_ik_labels(container_name)
                    joined.bake_fit_container_scale(container_name)
                    if original_up_axis == "y":
                        _refresh_fit_orientations_before_body(
                            joined, container_name)
                    fit_hierarchy = joined.capture_fit_hierarchy(container_name)
                    _preflight_centered_root_spine(joined, fit_hierarchy)
                    if original_up_axis == "z":
                        # MEL builds in Y-up, then rotates the finished Group
                        # back into the original Z-up scene.
                        joined.flip_character_scene_up_axis(container_name, "y")
                        _refresh_fit_orientations_before_body(
                            joined, container_name)
                        fit_hierarchy = joined.capture_fit_hierarchy(
                            container_name)
                    joined.write_missing_fit_deform_profiles(
                        container_name,
                        tuple(node.path for node in fit_hierarchy.joints),
                    )
                    preflight_registered_fit_parts(
                        joined, container_name,
                        include_segment_influences=include_segment_influences,
                        use_fit_part_hierarchy=use_fit_part_hierarchy,
                        fit_part_twist_sources=fit_part_twist_sources)
                    if joined.create_body_system_hierarchy(
                            include_dynamic=_include_dynamic) != _DEFORMATION_SYSTEM_PATH:
                        raise RuntimeError("Body 变形系统层级创建路径漂移")
                    fit_path = joined.parent_fit_skeleton_under_group(
                        container_name)
                    result = BuildRegisteredBodyCharacter(joined).apply(
                        fit_path, axial_description=axial_description,
                        include_head_aim=include_head_aim,
                        infer_missing_labels=infer_missing_labels,
                        include_segment_influences=include_segment_influences,
                        use_fit_part_hierarchy=use_fit_part_hierarchy,
                        fit_part_twist_sources=fit_part_twist_sources,
                        _hierarchy_prepared=True,
                        _scene_before=_scene_before,
                        _include_dynamic=_include_dynamic,
                        _defer_selection_sets=_defer_selection_sets,
                        _defer_all_set=_defer_all_set,
                        _retain_non_deform_markers=(
                            _retain_non_deform_markers),
                        _generic_fk_policy=_generic_fk_policy)
                    if original_up_axis == "z":
                        joined.flip_character_scene_up_axis("|Group", "z")
                        result = replace(
                            result,
                            registration=joined.rebase_character_registration_bind_pose(
                                result.registration),
                        )
                    return result
                finally:
                    if joined.scene_up_axis().value != original_up_axis:
                        joined.set_scene_up_axis(original_up_axis)
        preview = BuildOrientedBodySkeleton(self._host).plan(
            container_name, infer_missing_labels=infer_missing_labels,
            root_parent_path=_DEFORMATION_SYSTEM_PATH)
        if not preview.ready:
            raise FitSkeletonValidationError(
                "角色构建预检失败，场景未修改：" + "；".join(preview.blockers))
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
                fit_source.metadata,
                use_offset_parent_matrix=(
                    preview.build.build_options.use_offset_parent_matrix))
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
            fit_source = self._host.capture_fit_orientation(container_name)
            omitted_parts = tuple(
                item.joint for item in fit_source.metadata
                if (item.twist_joints or 0) > 0
                or (item.inbetween_joints or 0) > 0)
            if omitted_parts:
                raise FitSkeletonValidationError(
                    "Fit 已标记 Twist／Inbetween，不能在关闭 Fit 分段时构建："
                    + "、".join(omitted_parts))
            hip_selection = plan_hip_swing_fit_selection(
                fit_source,
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
            fit_part_hierarchy = (
                BuildFitPartHierarchy(joined).apply(part_plan)
                if use_fit_part_hierarchy else None)
            final_paths = (fit_part_hierarchy.final_paths
                           if fit_part_hierarchy is not None else None)
            if final_paths is not None and bendy_chains:
                bendy_chains = rebase_plan_paths_after_parts(
                    bendy_chains, final_paths)
            rig_host = (_PartAwareRigHost(joined, final_paths)
                        if final_paths is not None else joined)
            rig = BuildBodyCharacterRig(rig_host).apply(container_name,
                include_torso=True, include_spine_ik=True,
                include_control_spaces=True, axial_description=axial_description,
                include_head_aim=include_head_aim,
                defer_fit_tweakers=True,
                defer_curve_guides=True,
                defer_partial_hand_to_generic=True,
                part_paths=final_paths)
            if not use_fit_part_hierarchy:
                BuildFitPartScaleDrivers(joined).apply_terminal_only(
                    part_plan.specs,
                    frozenset(item.joint for item in fit_source.metadata
                              if item.ik_local_mode is not None),
                    frozenset(control.control_name
                              for control in rig.plan.leg.fk_controls.controls))
            early_bendy_chains, deferred_bendy_chains = (
                split_fit_bendy_chains(bendy_chains, rig.plan))
            if early_bendy_chains:
                early_bendy_follows = plan_fit_bendy_follow(
                    early_bendy_chains, rig.plan)
                BuildFitBendyGuides(joined).apply(
                    early_bendy_chains, follows=early_bendy_follows)
            twist_steps = ()
            scale_plan = None
            inbetween_segments = ()
            inbetween_parts = ()
            inbetween_bindings = ()
            solver_mapping = None
            inbetween_untwisters = ()
            hip_swing_reverse = None
            twist_projections = ()
            if use_fit_part_hierarchy:
                active_twist_parts = tuple(replace(
                    part,
                    start_body=final_paths.remap_body_reference(
                        part.start_body),
                    end_body=final_paths.remap_body_reference(
                        part.end_body),
                ) for part in ordinary_twist_parts)
                (control_matrices, body_constraints,
                 blended_matrices, root_child_offsets) = (
                    _independent_rig_twist_sources(rig.plan))
                if fit_part_twist_sources is None:
                    rotation_inputs = plan_standard_fit_part_rotation_inputs(
                        active_twist_parts,
                        independent_world_matrices=control_matrices,
                        independent_body_constraints=body_constraints,
                        blended_world_matrices=blended_matrices,
                        reference_inverse_matrices={
                            part.start_body: root_child_offsets[part.start_body]
                            for part in active_twist_parts
                            if part.start_body in root_child_offsets},
                        semantic_parent_by_body={
                            final_paths.remap_body_reference(spec.path):
                            final_paths.remap_body_reference(spec.parent_path)
                            for spec in part_plan.specs
                            if spec.parent_path is not None},
                    )
                    projections = plan_fit_part_twist_projections(
                        rotation_inputs)
                    twist_projections = projections
                    plan_fit_part_twist(
                        active_twist_parts,
                        tuple(item.source() for item in projections
                              if item.input.distribution_source))
                twist_sources = (
                    PrepareFitPartTwistSources(joined).apply(rotation_inputs)
                    if fit_part_twist_sources is None
                    else fit_part_twist_sources
                )
                if fit_part_twist_sources is None:
                    PrepareFitPartTwistSources(joined).assert_reparented_static_sources(
                        projections, final_paths)
                active_twist_sources = tuple(replace(
                    source,
                    start_body=final_paths.remap_body_reference(
                        source.start_body),
                    down_twist_plug=final_paths.remap_body_reference(
                        source.down_twist_plug),
                    up_twist_plug=(final_paths.remap_body_reference(
                        source.up_twist_plug) if source.up_twist_plug else None),
                ) for source in twist_sources)
                twist_steps = BuildFitPartTwistDrivers(joined).apply(
                    active_twist_parts, active_twist_sources)
                scale_plan = BuildFitPartScaleDrivers(joined).apply(
                    part_plan.fit_parts, part_plan.specs,
                    frozenset(item.joint for item in fit_source.metadata
                              if item.ik_local_mode is not None),
                    frozenset(control.control_name
                              for control in rig.plan.leg.fk_controls.controls))
                if early_bendy_chains:
                    BuildFitBendyDeform(joined).apply(early_bendy_chains)
                inbetween_parts = tuple(
                    part for part in part_plan.fit_parts
                    if part.kind == "inbetween")
                if inbetween_parts:
                    bindings = plan_inbetween_limb_bindings(
                        inbetween_parts, rig.plan,
                        final_paths=final_paths,
                        defer_generic=True)
                    inbetween_bindings = bindings
                    limb_bindings = tuple(
                        binding for binding in bindings
                        if isinstance(binding, InbetweenLimbBinding))
                    bulk = BuildInbetweenLimbSegments(joined).apply(
                        limb_bindings, rig.plan,
                        sub_controllers=(
                            preview.build.build_options.sub_controllers),
                        extra_controllers=(
                            preview.build.build_options.extra_controllers))
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
                                    start_fk_source_path=(
                                        binding.start_fk_source_path),
                                    downstream_fk_offset_path=(
                                        binding.downstream_fk_offset_path),
                                    rotate_order=binding.rotate_order,
                                    part_control_radius=(
                                        binding.part_control_radius),
                                    sub_controllers=(
                                        preview.build.build_options.sub_controllers),
                                    extra_controllers=(
                                        preview.build.build_options.extra_controllers),
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
            fit_metadata = rig.plan.arm.safety.symmetry.source.metadata
            standard_fk_specs = (
                rig.plan.arm.fk_controls.controls
                + rig.plan.leg.fk_controls.controls
                + (rig.plan.hand.controls.controls
                   if rig.plan.hand is not None else ())
                + (rig.plan.torso.torso.controls.controls
                   if rig.plan.torso is not None else ()))
            handled_inbetween_starts = frozenset(
                binding.parts[0].start_body
                for binding in inbetween_bindings)
            generic_fk = plan_body_generic_fk(
                skeleton.snapshot, part_plan.specs,
                fit_metadata, standard_fk_specs,
                sub_controllers=(
                    preview.build.build_options.sub_controllers),
                extra_controllers=(
                    preview.build.build_options.extra_controllers),
                use_offset_parent_matrix=(
                    preview.build.build_options.use_offset_parent_matrix),
                aim_sources=(_generic_fk_policy.aim_sources
                             if _generic_fk_policy is not None else None),
                inbetween_start_paths=frozenset(
                    part.start_body for part in inbetween_parts
                    if part.start_body not in handled_inbetween_starts),
                remapped_body_paths=(
                    {spec.path: final_paths.remap_body_reference(spec.path)
                     for spec in part_plan.specs}
                    if final_paths is not None else None),
                root_follow_transform=(
                    rig.plan.torso.torso.leg_lock.path
                    if rig.plan.torso is not None else None),
                follower_sources=(
                    _generic_fk_policy.follower_sources
                    if _generic_fk_policy is not None else None),
                finger_visibility_plug=(
                    rig.plan.global_control.control_path + ".fingerVis"))
            generic_inbetween_bindings = (
                plan_generic_inbetween_fk_bindings(
                    inbetween_parts, generic_fk, standard_fk_specs,
                    final_paths=final_paths,
                    handled_start_paths=handled_inbetween_starts)
                if inbetween_parts and final_paths is not None else ())
            fit_hierarchy = rig.plan.arm.safety.symmetry.source.hierarchy
            fit_parents = {joint.dag_parent
                           for joint in fit_hierarchy.joints}
            source_by_body = {
                (final_paths.remap_body_reference(spec.path)
                 if final_paths is not None else spec.path): spec.source_joint
                for spec in part_plan.specs}
            generic_fk_locks = []
            for control in generic_fk.controls:
                source_joint = source_by_body.get(control.driven_joint)
                if source_joint is None:
                    raise RuntimeError("通用 FK 缺少精确 Fit 来源："
                                       + control.control_name)
                if source_joint in fit_parents:
                    attributes = joined.read_fit_fk_lock_channels(
                        source_joint)
                    if attributes:
                        generic_fk_locks.append(BodyFkChannelLockSpec(
                            control.control_path, source_joint, attributes))
            generic_fk_locks = tuple(generic_fk_locks)
            joined.create_body_generic_fk(generic_fk)
            if not joined.capture_body_generic_fk_followers(generic_fk):
                raise RuntimeError("通用 FK 从混合 Body 父链分出的跟随层不一致")
            if generic_fk.controls:
                generic_fk_state = joined.capture_body_generic_fk_controls(
                    generic_fk)
                generic_fk_issues = audit_body_limb_fk_controls(
                    generic_fk, generic_fk_state,
                    limb_label="Generic")
                if generic_fk_issues:
                    raise RuntimeError(
                        "通用 FK 控制层不一致：" + "；".join(
                            issue.message for issue in generic_fk_issues))
                if any(not joined.capture_hidden_body_fk_control(path)
                       for path in generic_fk.hidden_controls):
                    raise RuntimeError("通用 FK noControl 隐藏状态不一致")
            if generic_inbetween_bindings:
                generic_segments = tuple(
                    BuildInbetweenFkSegment(joined).apply(
                        binding.parts,
                        fk_offset_path=binding.fk_offset_path,
                        fk_control_path=binding.fk_control_path,
                        fk_system_path=binding.fk_system_path,
                        start_fk_driver_path=binding.start_fk_driver_path,
                        start_fk_constraint_name=(
                            binding.start_fk_constraint_name),
                        start_fk_source_path=(
                            binding.start_fk_source_path),
                        downstream_fk_offset_path=(
                            binding.downstream_fk_offset_path),
                        rotate_order=binding.rotate_order,
                        part_control_radius=binding.part_control_radius,
                        sub_controllers=(
                            preview.build.build_options.sub_controllers),
                        extra_controllers=(
                            preview.build.build_options.extra_controllers))
                    for binding in generic_inbetween_bindings)
                inbetween_segments += generic_segments
                for binding in generic_inbetween_bindings:
                    if (binding.parts[0].source_joint in untwister_sources
                            and (binding.end_fk_control_path is None
                                 or binding.downstream_fk_offset_path is None)):
                        raise ValueError(
                            "附加 Inbetween UnTwister 缺少下游 FK 控制")
                inbetween_untwisters += tuple(
                    BuildInbetweenUnTwister(joined).apply(
                        binding.parts,
                        tuple(item.constraint_name
                              for item in segment.body.parts),
                        end_fk_control_path=binding.end_fk_control_path,
                        end_fk_offset_path=(
                            binding.downstream_fk_offset_path))
                    for binding, segment in zip(
                        generic_inbetween_bindings, generic_segments)
                    if binding.parts[0].source_joint in untwister_sources)
                rewired = {
                    segment.rewire.start_fk_constraint_name:
                    segment.fk.anchor.fk_offset_path + "|"
                    + segment.fk.anchor.fkx_name
                    for segment in generic_segments}
                generic_fk = replace(generic_fk, controls=tuple(
                    replace(control, source_override_path=(
                        rewired.get(control.constraint_name,
                                    control.source_override_path)))
                    for control in generic_fk.controls))
                generic_fk_state = joined.capture_body_generic_fk_controls(
                    generic_fk)
                if audit_body_limb_fk_controls(
                        generic_fk, generic_fk_state,
                        limb_label="Generic", check_initial_pose=False):
                    raise RuntimeError(
                        "附加 Inbetween 改接后通用 FK 控制层不一致")
                if not body_bind_pose_matches(
                        skeleton.snapshot,
                        joined.capture_body_skeleton(skeleton.snapshot.root)):
                    raise RuntimeError(
                        "附加 Inbetween 改接改变 Body 绑定姿态")
            twist_rewires = plan_generic_fit_part_twist_rewires(
                twist_projections, generic_fk.controls)
            if (_generic_fk_policy is not None
                    and _generic_fk_policy.twist_rewired_sources is not None):
                twist_rewires = tuple(
                    spec for spec in twist_rewires
                    if spec.start_body.rsplit("|", 1)[-1]
                    .rsplit(":", 1)[-1] in
                    _generic_fk_policy.twist_rewired_sources)
            if twist_rewires:
                before_twist_rewire = joined.capture_body_skeleton(
                    skeleton.snapshot.root)
                AttachGenericFitPartTwistSources(joined).apply(
                    twist_rewires)
                if not body_skeleton_unchanged(
                        before_twist_rewire,
                        joined.capture_body_skeleton(skeleton.snapshot.root),
                        tolerance=1e-4):
                    raise RuntimeError(
                        "通用 FK Twist 来源改接改变 Body 绑定姿态")
            if deferred_bendy_chains:
                bendy_follows = plan_fit_bendy_follow(
                    deferred_bendy_chains, rig.plan, generic_fk.controls)
                BuildFitBendyGuides(joined).apply(
                    deferred_bendy_chains, follows=bendy_follows)
                BuildFitBendyDeform(joined).apply(deferred_bendy_chains)
                bendy_fk_scales = plan_fit_bendy_fk_scales(
                    deferred_bendy_chains, generic_fk.controls)
                BuildFitBendyFkScales(joined).apply(bendy_fk_scales)
                if not body_bind_pose_matches(
                        skeleton.snapshot,
                        joined.capture_body_skeleton(skeleton.snapshot.root)):
                    raise RuntimeError("Bendy 接管改变 Body 绑定姿态")
            scale_controls = tuple(
                control for control in generic_fk.controls
                if control.driven_joint not in {
                    chain.start_body for chain in bendy_chains}
                if (_generic_fk_policy is None
                    or _generic_fk_policy.scale_controls is None
                    or control.control_path in
                    _generic_fk_policy.scale_controls))
            generic_direct_scales = plan_body_direct_fk_scales(
                skeleton.snapshot, scale_controls)
            for scale_spec in generic_direct_scales:
                joined.preflight_body_direct_fk_scale(scale_spec)
            for scale_spec in generic_direct_scales:
                joined.connect_body_direct_fk_scale(scale_spec)
            if any(not joined.capture_body_direct_fk_scale(scale_spec)
                   for scale_spec in generic_direct_scales):
                raise RuntimeError("通用 FK 缩放未连接到 Body 关节")
            generic_scale_compensations = ()
            if (generic_fk.controls and
                    (_generic_fk_policy is None
                     or _generic_fk_policy.compensated_controls is None
                     or _generic_fk_policy.compensated_controls)):
                symmetry_instances = (
                    rebase_plan_paths_after_parts(
                        part_plan.symmetry.instances, final_paths)
                    if final_paths is not None else
                    part_plan.symmetry.instances)
                spline = (rig.plan.torso.torso.spline
                          if rig.plan.torso is not None else None)
                spline_sources = tuple(
                    (joint.path, joint.source_joint)
                    for joint in spline.joints[:len(spline.body_joints)]
                ) if spline is not None else ()
                generic_control_paths = {
                    control.control_path for control in generic_fk.controls}
                all_fk_scale_compensations = plan_body_fk_scale_compensation(
                    standard_fk_specs + generic_fk.controls,
                    symmetry_instances, fit_metadata,
                    use_offset_parent_matrix=BodyBuildOptions.from_fit_settings(
                        rig.plan.arm.safety.symmetry.settings
                    ).use_offset_parent_matrix,
                    finger_control_paths=frozenset(
                        control.control_path for control in
                        standard_fk_specs + generic_fk.controls
                        if any(re.fullmatch(
                            r"(?:Thumb|Index|Middle|Ring|Pinky)(?:[1-4]|End)",
                            name.removesuffix("_NonSymmetry"))
                            for name in control.fit_joint_names)),
                    generated_joint_sources=spline_sources)
                generic_scale_specs = []
                for spec in all_fk_scale_compensations:
                    if (spec.control_path not in generic_control_paths
                            or (_generic_fk_policy is not None
                                and _generic_fk_policy.compensated_controls
                                is not None
                                and spec.control_path not in
                                _generic_fk_policy.compensated_controls)):
                        continue
                    independent = (
                        preview.build.build_options.use_offset_parent_matrix
                        and (_generic_fk_policy is None
                             or _generic_fk_policy.independent_controls is None
                             or spec.control_path in
                             _generic_fk_policy.independent_controls))
                    generic_scale_specs.append(replace(
                        spec, independent_parent=independent,
                        main_scale_source_path=(
                            rig.plan.global_control.control_path
                            if independent else None)))
                generic_scale_compensations = tuple(generic_scale_specs)
                BuildBodyFkScaleCompensation(joined).apply(
                    generic_scale_compensations)
            if generic_direct_scales or generic_scale_compensations:
                rig = replace(rig, plan=replace(rig.plan,
                    direct_fk_scales=(rig.plan.direct_fk_scales
                                      + generic_direct_scales),
                    fk_scale_compensations=(rig.plan.fk_scale_compensations
                                            + generic_scale_compensations)))
            generic_fk_globals = plan_body_fk_global(
                fit_metadata, tuple(control for control in
                    generic_fk.controls
                    if (_generic_fk_policy is None
                        or _generic_fk_policy.global_controls is None
                        or control.control_path in
                        _generic_fk_policy.global_controls)))
            for global_spec in generic_fk_globals:
                joined.create_body_fk_global(global_spec)
            generic_global_states = tuple(
                joined.capture_body_fk_global(global_spec)
                for global_spec in generic_fk_globals)
            if any(audit_body_fk_global(global_spec, state)
                   for global_spec, state in zip(generic_fk_globals,
                                                 generic_global_states)):
                raise RuntimeError("通用 FK Global 矩阵层构建后复检失败")
            if generic_fk_globals:
                rig = replace(rig,
                    plan=replace(rig.plan,
                        fk_globals=rig.plan.fk_globals
                                   + generic_fk_globals),
                    fk_globals=rig.fk_globals + generic_global_states)
            generic_aim_names = {
                name for control in generic_fk.controls
                if control.aim_path is not None
                for name in control.fit_joint_names}
            generic_aim_metadata = tuple(
                item for item in fit_metadata
                if (FitJointField.AIM in item.present_fields
                    and item.joint in fit_parents
                    and item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                    in generic_aim_names
                    and (_generic_fk_policy is None
                         or _generic_fk_policy.aim_sources is None
                         or item.joint.rsplit("|", 1)[-1]
                         .rsplit(":", 1)[-1] in
                         _generic_fk_policy.aim_sources)))
            marked_generic_names = {
                item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                for item in generic_aim_metadata}
            generic_aim_controls = tuple(
                control for control in generic_fk.controls
                if (control.aim_path is not None
                    and marked_generic_names.intersection(
                        control.fit_joint_names)))
            generic_fit_aim = plan_body_fit_aim(
                fit_hierarchy, generic_aim_metadata,
                skeleton.snapshot, generic_aim_controls)
            aim_use_opm = BodyBuildOptions.from_fit_settings(
                rig.plan.arm.safety.symmetry.settings
            ).use_offset_parent_matrix
            for aim_spec in generic_fit_aim:
                joined.create_body_fit_aim(
                    aim_spec,
                    global_control=rig.plan.global_control.control_path,
                    use_offset_parent_matrix=aim_use_opm)
            if any(not joined.capture_body_fit_aim(
                    aim_spec,
                    global_control=rig.plan.global_control.control_path,
                    use_offset_parent_matrix=aim_use_opm)
                   for aim_spec in generic_fit_aim):
                raise RuntimeError("通用 FK Fit Aim 构建后复检失败")
            if generic_fit_aim:
                rig = replace(rig, plan=replace(rig.plan,
                    fit_aim=rig.plan.fit_aim + generic_fit_aim))
            fk_control_specs = (standard_fk_specs
                                + generic_fk.controls)
            pre_constraint_body = joined.capture_body_skeleton(
                skeleton.snapshot.root)
            wheels = plan_body_fit_wheels(
                fit_metadata, part_plan.symmetry.instances,
                fk_control_specs,
                scale_plug=(rig.plan.global_control.scale_node_name
                            + ".input1Y"))
            curve_guides = plan_body_fit_curve_guides(
                fit_metadata, part_plan.symmetry.instances,
                part_plan.specs, fk_control_specs,
                final_paths=final_paths)
            root_x = (rig.plan.torso.torso.root_x
                      if rig.plan.torso is not None else None)
            center_plan = plan_body_center_between_feet(
                fit_metadata, root_x, rig.plan.leg.ik.limbs)
            if center_plan is not None and any(
                    item.ik_follow is not None
                    and item.joint.rsplit("|", 1)[-1].rsplit(
                        ":", 1)[-1] in {"Ankle", "Toes", "ToesEnd"}
                    for item in fit_metadata):
                raise ValueError(
                    "Center Between Feet 与脚部 IK Follow 不能同时启用")
            center_between_feet = BuildCenterBetweenFeet(joined).apply(
                fit_metadata, root_x, rig.plan.leg.ik.limbs)
            if center_between_feet is not None and not body_skeleton_unchanged(
                    pre_constraint_body,
                    joined.capture_body_skeleton(skeleton.snapshot.root),
                    tolerance=1e-4):
                raise RuntimeError("Center Between Feet 改变了 Body 绑定姿态")
            if root_x is None and any(item.follow_spaces
                                      for item in fit_metadata):
                raise ValueError("Follow Spaces 需要 RootX 控制层")
            follow_spaces_plan = plan_body_fit_follow_spaces(
                fit_metadata, fk_control_specs, pre_constraint_body.joints,
                main_path=rig.plan.global_control.control_path,
                main_extra_paths=rig.plan.global_control.extra_control_paths,
                root_path=root_x.control_path if root_x is not None else "")
            fk_drivers = {
                path: control.driven_joint
                for control in fk_control_specs
                for path in (control.control_path,
                             control.source_override_path)
                if path is not None
            }
            follow_space_edges = tuple(
                (spec.source_body, tuple(
                    fk_drivers.get(target.source, target.source)
                    for target in spec.targets))
                for spec in follow_spaces_plan)
            named_follow_plan = plan_body_fit_named_follow(
                fit_metadata, fk_control_specs, pre_constraint_body.joints)
            named_follow_edges = tuple(
                (spec.source_body,
                 joined.resolve_body_fit_named_follow_targets(spec))
                for spec in named_follow_plan)
            ik_follow_plan = plan_body_fit_ik_follow(
                fit_metadata, rig.plan.arm.ik.limbs,
                rig.plan.leg.ik.limbs, pre_constraint_body.joints,
                spine=(rig.plan.torso.torso.spine
                       if rig.plan.torso is not None else None),
                spline=(rig.plan.torso.torso.spline
                        if rig.plan.torso is not None else None))
            aim_at_plan = plan_body_fit_aim_at(
                fit_metadata, fk_control_specs, pre_constraint_body.joints)
            plan_body_fit_geo_attach(
                fit_metadata, fk_control_specs, pre_constraint_body.joints)
            plan_body_fit_proximity_pin(
                fit_metadata, fk_control_specs, pre_constraint_body.joints)
            validate_fit_control_dependencies(
                plan_body_fit_advanced_constraints(
                    fit_metadata, fk_control_specs, pre_constraint_body.joints),
                plan_body_fit_follow(
                    fit_metadata, fk_control_specs,
                    pre_constraint_body.joints) + ik_follow_plan,
                named_follow_edges + follow_space_edges + tuple(
                    (spec.source_body, (spec.target_body,))
                    for spec in aim_at_plan))
            advanced_constraints = BuildFitAdvancedConstraints(joined).apply(
                fit_metadata,
                fk_control_specs,
                pre_constraint_body.joints)
            if advanced_constraints and not body_skeleton_unchanged(
                    pre_constraint_body,
                    joined.capture_body_skeleton(skeleton.snapshot.root),
                    tolerance=1e-4):
                raise RuntimeError(
                    "Advanced Constraint 改变了 Body 绑定姿态")
            pre_follow_body = joined.capture_body_skeleton(
                skeleton.snapshot.root)
            fit_follows = BuildFitFollow(joined).apply(
                fit_metadata,
                fk_control_specs, pre_follow_body.joints)
            if fit_follows and not body_skeleton_unchanged(
                    pre_follow_body,
                    joined.capture_body_skeleton(skeleton.snapshot.root),
                    tolerance=1e-4):
                raise RuntimeError("Fit Follow 改变了 Body 绑定姿态")
            pre_named_follow_body = joined.capture_body_skeleton(
                skeleton.snapshot.root)
            named_follows = BuildFitNamedFollow(joined).apply(
                fit_metadata, fk_control_specs, pre_named_follow_body.joints)
            if named_follows and not body_skeleton_unchanged(
                    pre_named_follow_body,
                    joined.capture_body_skeleton(skeleton.snapshot.root),
                    tolerance=1e-4):
                raise RuntimeError("Fit Follow* 改变了 Body 绑定姿态")
            pre_follow_spaces_body = joined.capture_body_skeleton(
                skeleton.snapshot.root)
            follow_spaces = BuildFitFollowSpaces(joined).apply(
                fit_metadata, fk_control_specs,
                pre_follow_spaces_body.joints,
                main_path=rig.plan.global_control.control_path,
                main_extra_paths=rig.plan.global_control.extra_control_paths,
                root_path=root_x.control_path if root_x is not None else "")
            if follow_spaces and not body_skeleton_unchanged(
                    pre_follow_spaces_body,
                    joined.capture_body_skeleton(skeleton.snapshot.root),
                    tolerance=1e-4):
                raise RuntimeError("Fit Follow Spaces 改变了 Body 绑定姿态")
            pre_ik_follow_body = joined.capture_body_skeleton(
                skeleton.snapshot.root)
            ik_follows = BuildFitIkFollow(joined).apply(
                fit_metadata, rig.plan.arm.ik.limbs,
                rig.plan.leg.ik.limbs, pre_ik_follow_body.joints,
                spine=(rig.plan.torso.torso.spine
                       if rig.plan.torso is not None else None),
                spline=(rig.plan.torso.torso.spline
                        if rig.plan.torso is not None else None))
            if ik_follows and not body_skeleton_unchanged(
                    pre_ik_follow_body,
                    joined.capture_body_skeleton(skeleton.snapshot.root),
                    tolerance=1e-4):
                raise RuntimeError("Fit IK Follow 改变了 Body 绑定姿态")
            pre_aim_at_body = joined.capture_body_skeleton(
                skeleton.snapshot.root)
            aim_at_specs = BuildFitAimAt(joined).apply(
                fit_metadata, fk_control_specs, pre_aim_at_body.joints)
            if aim_at_specs and not body_skeleton_unchanged(
                    pre_aim_at_body,
                    joined.capture_body_skeleton(skeleton.snapshot.root),
                    tolerance=1e-4):
                raise RuntimeError("Fit AimAt 改变了 Body 绑定姿态")
            pre_geo_attach_body = joined.capture_body_skeleton(
                skeleton.snapshot.root)
            geo_attach_specs = BuildFitGeoAttach(joined).apply(
                fit_metadata, fk_control_specs, pre_geo_attach_body.joints)
            if geo_attach_specs and not body_skeleton_unchanged(
                    pre_geo_attach_body,
                    joined.capture_body_skeleton(skeleton.snapshot.root),
                    tolerance=1e-4):
                raise RuntimeError("Fit Geo Attach 改变了 Body 绑定姿态")
            pre_proximity_pin_body = joined.capture_body_skeleton(
                skeleton.snapshot.root)
            proximity_pin_specs = BuildFitProximityPin(joined).apply(
                fit_metadata, fk_control_specs,
                pre_proximity_pin_body.joints)
            if proximity_pin_specs and not body_skeleton_unchanged(
                    pre_proximity_pin_body,
                    joined.capture_body_skeleton(skeleton.snapshot.root),
                    tolerance=1e-4):
                raise RuntimeError("Fit Proximity Pin 改变了 Body 绑定姿态")
            tweakers = None
            if preview.build.build_options.use_offset_parent_matrix:
                tweakers = plan_fit_tweakers(
                    part_plan.symmetry.instances,
                    part_plan.symmetry.source.metadata,
                    part_plan.fit_parts if fit_part_hierarchy is not None else (),
                    motion_system_path=(
                        rig.plan.global_control.root_path.rsplit("|", 2)[0]),
                    global_control_path=rig.plan.global_control.control_path,
                    body_profiles={spec.path: spec.deform_profile
                                   for spec in part_plan.specs},
                    final_paths=(fit_part_hierarchy.final_paths
                                 if fit_part_hierarchy is not None else None))
                BuildFitTweakers(joined).apply(tweakers)
            built_curve_guides = (
                joined.create_body_fit_curve_guides(
                    curve_guides,
                    main_control=rig.plan.global_control.control_path,
                    fit_container=(rig.plan.arm.safety.symmetry.source
                                   .hierarchy.container))
                if curve_guides else ())
            if wheels:
                joined.create_body_fit_wheels(wheels)
            wheel_rig_plan = _with_wheel_fk_sources(rig.plan, wheels)
            if wheel_rig_plan != rig.plan:
                arm_fk = joined.capture_body_arm_fk_controls(
                    wheel_rig_plan.arm.fk_controls)
                leg_fk = joined.capture_body_leg_fk_controls(
                    wheel_rig_plan.leg.fk_controls)
                fk_issues = tuple(audit_body_limb_fk_controls(
                    wheel_rig_plan.arm.fk_controls, arm_fk,
                    limb_label="Arm")) + tuple(audit_body_limb_fk_controls(
                        wheel_rig_plan.leg.fk_controls, leg_fk,
                        limb_label="Leg"))
                if fk_issues:
                    raise RuntimeError(
                        "Wheel FK 改接后控制层不一致："
                        + "；".join(issue.message for issue in fk_issues))
                hand_result = rig.hand
                if wheel_rig_plan.hand is not None and hand_result is not None:
                    hand_fk = joined.capture_body_hand_fk_controls(
                        wheel_rig_plan.hand.controls)
                    if audit_body_hand_fk_controls(
                            wheel_rig_plan.hand.controls, hand_fk):
                        raise RuntimeError("Wheel Hand FK 改接后控制层不一致")
                    hand_result = replace(
                        hand_result, plan=wheel_rig_plan.hand,
                        snapshot=hand_fk)
                torso_result = rig.torso
                if wheel_rig_plan.torso is not None:
                    torso_result = joined.capture_body_torso(
                        wheel_rig_plan.torso.torso)
                    if audit_body_torso(wheel_rig_plan.torso.torso,
                                        torso_result):
                        raise RuntimeError("Wheel Torso FK 改接后控制层不一致")
                rig = replace(
                    rig, plan=wheel_rig_plan,
                    arm=replace(rig.arm, plan=wheel_rig_plan.arm,
                                fk_controls=arm_fk),
                    leg=replace(rig.leg, plan=wheel_rig_plan.leg,
                                fk_controls=leg_fk),
                    hand=hand_result, torso=torso_result)
            for lock_spec in generic_fk_locks:
                joined.apply_body_fk_channel_locks(lock_spec)
            if any(not joined.capture_body_fk_channel_locks(lock_spec)
                   for lock_spec in generic_fk_locks):
                raise RuntimeError("通用 FK 的来源通道锁定未生效")
            if generic_fk_locks:
                rig = replace(rig, plan=replace(rig.plan,
                    fk_channel_locks=(rig.plan.fk_channel_locks
                                      + generic_fk_locks)))
            # 6.925 builds Heel/BigToe/PinkyToe as temporary Body joints so
            # Foot Roll and Rock can read their frames, then removes them
            # before DeformSet, buildPose and the final character registry.
            non_deform = (() if _retain_non_deform_markers else
                          plan_body_non_deform_markers(rig.body))
            if non_deform:
                final_marker_body = joined.remove_body_non_deform_markers(
                    skeleton.snapshot.root, non_deform)
                provenance = oriented_body_provenance(
                    skeleton.plan.provenance.source_container,
                    len(final_marker_body.joints))
                skeleton = replace(
                    skeleton,
                    plan=replace(skeleton.plan, provenance=provenance),
                    snapshot=final_marker_body)
                rig = replace(
                    rig, body=final_marker_body,
                    arm=replace(rig.arm, body=final_marker_body),
                    leg=replace(rig.leg, body=final_marker_body),
                    hand=(replace(rig.hand, body=final_marker_body)
                          if rig.hand is not None else None))
            registration = RegisterBodyCharacter(joined).apply(rig)
            registration = RegisterGenericFk(joined).apply(
                registration, generic_fk, generic_fk_locks)
            registration = RegisterFitCurveGuides(joined).apply(
                registration, built_curve_guides,
                main_control=rig.plan.global_control.control_path)
            registration = RegisterFitWheels(joined).apply(
                registration, wheels)
            registration = RegisterFitAdvancedConstraints(joined).apply(
                registration, advanced_constraints)
            registration = RegisterFitFollow(joined).apply(
                registration, fit_follows)
            registration = RegisterFitNamedFollow(joined).apply(
                registration, named_follows)
            registration = RegisterFitFollowSpaces(joined).apply(
                registration, follow_spaces)
            registration = RegisterFitIkFollow(joined).apply(
                registration, ik_follows)
            registration = RegisterFitAimAt(joined).apply(
                registration, aim_at_specs)
            registration = RegisterFitGeoAttach(joined).apply(
                registration, geo_attach_specs)
            registration = RegisterFitProximityPin(joined).apply(
                registration, proximity_pin_specs)
            registration = RegisterCenterBetweenFeet(joined).apply(
                registration, center_between_feet)
            if tweakers is not None:
                registration = RegisterFitTweakers(joined).apply(
                    registration, tweakers)
            if (fit_part_hierarchy is not None
                    and (twist_steps or (scale_plan is not None
                                         and scale_plan.limbs))):
                ik_paths = tuple(
                    limb.wrist_control_path
                    for limb in rig.plan.arm.ik.limbs) + tuple(
                    limb.ankle_control_path
                    for limb in rig.plan.leg.ik.limbs)
                ik_control_paths = {
                    path.rsplit("|", 1)[-1]: path
                    for path in ik_paths
                }
                if len(ik_control_paths) != len(ik_paths):
                    raise ValueError("Fit Part IK 控制器名称重复")
                registration = RegisterFitPartChannels(joined).apply(
                    registration, twist_steps,
                    fit_part_hierarchy.final_paths,
                    scale_plan, ik_control_paths)
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
            # ADV switches Foot limbs to IK only after their handles, pivots,
            # and secondary controls are complete.  Capture that final mode
            # in buildPose rather than recording the temporary FK build mode.
            joined.set_body_leg_initial_ik(rig.plan.leg.blend)
            final_leg_blend = joined.capture_body_leg_blend(
                rig.plan.leg.blend)
            if audit_body_leg_blend(rig.plan.leg.blend, final_leg_blend,
                                    expected_attribute_value=1.0):
                raise RuntimeError("Leg 默认 IK 模式或约束连接不一致")
            final_body = joined.capture_body_skeleton(skeleton.snapshot.root)
            if not body_bind_pose_matches(skeleton.snapshot, final_body):
                raise RuntimeError("Leg 切换默认 IK 后 Body 绑定姿态改变")
            rig = replace(rig, leg=replace(rig.leg, blend=final_leg_blend),
                          body=final_body)
            selection_extras = tuple(
                extra for chain in bendy_chains
                for extra in chain.micro_extra_names) + tuple(
                    control.extra_path or control.control_path
                    for control in generic_fk.controls
                    if control.control_path not in generic_fk.hidden_controls)
            if not _defer_selection_sets:
                finalize_body_character_sets(
                    joined, registration, rig.plan,
                    segments=tuple(segments), extras=selection_extras,
                    populate_all=False)
            joined.finalize_fit_skeleton_visibility(container_name)
            hierarchy = joined.capture_body_system_hierarchy(
                skeleton.snapshot.root, container_name,
                include_dynamic=_include_dynamic)
            if hierarchy != expected_body_system_hierarchy(
                    skeleton.snapshot.root, container_name,
                    include_dynamic=_include_dynamic):
                raise RuntimeError("角色主构建结束时 Body 变形系统层级不一致")
            if (_scene_before is not None and not _defer_selection_sets
                    and not _defer_all_set):
                finalize_body_character_sets(
                    joined, registration, rig.plan,
                    scene_before=_scene_before,
                    fit_container=container_name, create_sets=False)
        return RegisteredBodyBuildResult(
            skeleton, rig, registration, tuple(segments),
            fit_part_hierarchy, inbetween_segments,
            inbetween_untwisters, hip_swing_reverse,
            solver_mapping, selection_extras,
            curve_guides=built_curve_guides, wheels=wheels)
