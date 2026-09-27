"""Build and register a complete Body character in one host transaction."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_part import rebase_plan_paths_after_parts
from adv_py.core.fit_part_twist import (
    FitPartTwistSource, plan_fit_part_twist,
    plan_fit_part_twist_projections,
    plan_standard_fit_part_rotation_inputs,
)

from .axial_part_deform import BuildAxialPartDeform
from .body_character_rig import BuildBodyCharacterRig, BodyCharacterRigBuildResult
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
    InbetweenFkBinding, plan_inbetween_limb_bindings,
)
from .fit_inbetween_limb_segment import (
    BuildInbetweenLimbSegment, InbetweenLimbSegmentResult,
)
from .fit_inbetween_fk_segment import (
    BuildInbetweenFkSegment, InbetweenFkSegmentResult,
)
from .fit_inbetween_registration import RegisterInbetweenControls
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


@dataclass(frozen=True, slots=True)
class RegisteredBodyBuildResult:
    skeleton: OrientedBodySkeletonBuildResult
    rig: BodyCharacterRigBuildResult
    registration: CharacterRegistration
    segment_influences: tuple[str, ...] = ()
    fit_part_hierarchy: FitPartHierarchyResult | None = None
    inbetween_segments: tuple[
        InbetweenLimbSegmentResult | InbetweenFkSegmentResult, ...] = ()


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
        part_plan = preview.build
        if use_fit_part_hierarchy:
            _, inbetween_plan = PrepareFitInbetween(self._host).plan(
                container_name)
            if inbetween_plan.guides:
                part_plan = plan_combined_part_hierarchy(
                    preview.build, inbetween_plan)
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
                        inbetween_parts, rig.plan)
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
                        built_segments.append(
                            BuildInbetweenLimbSegment(joined).apply(
                                binding.parts,
                                fk_offset_path=binding.fk_offset_path,
                                fk_control_path=binding.fk_control_path,
                                fk_system_path=binding.fk_system_path,
                                start_fk_driver_path=(
                                    binding.start_fk_driver_path),
                                start_fk_constraint_name=(
                                    binding.start_fk_constraint_name),
                                downstream_fk_offset_path=(
                                    binding.downstream_fk_offset_path),
                                start_ik_driver=binding.start_ik_driver,
                                end_ik_driver=binding.end_ik_driver,
                                fk_weight_plug=binding.fk_weight_plug,
                                ik_weight_plug=binding.ik_weight_plug,
                                rotate_order=binding.rotate_order,
                                part_control_radius=(
                                    binding.part_control_radius),
                            ))
                    inbetween_segments = tuple(built_segments)
                driven_body = joined.capture_body_skeleton(
                    skeleton.snapshot.root)
                if not body_bind_pose_matches(
                        fit_part_hierarchy.body, driven_body):
                    raise RuntimeError("Fit Part 驱动改变了 Body 绑定姿态")
                rig = replace(
                    rig,
                    plan=rebase_plan_paths_after_parts(
                        rig.plan, final_paths),
                    body=driven_body,
                )
            registration = RegisterBodyCharacter(joined).apply(rig)
            if inbetween_segments:
                registration = RegisterInbetweenControls(joined).apply(
                    registration, inbetween_segments)
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
            fit_part_hierarchy, inbetween_segments)
