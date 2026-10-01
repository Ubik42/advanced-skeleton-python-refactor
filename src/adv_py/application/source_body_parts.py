"""Attach existing Part twist and scale drivers to real source rig outputs."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.fit_part_twist import plan_standard_fit_part_rotation_inputs
from .fit_part_twist import PrepareFitPartTwistSources, BuildFitPartTwistDrivers
from .fit_part_scale import BuildFitPartScaleDrivers
from .fit_bendy import (
    FitBendyWorldSource, plan_fit_bendy_follow,
    BuildFitBendyGuides, BuildFitBendyDeform,
)


def build_source_body_part_drivers(host, build, part_result, fk, limbs, spline, bendy_chains=(), inbetween_segments=()):
    if part_result is None:
        return (), None, ()
    paths = part_result.final_paths
    spline_plans=spline if isinstance(spline,tuple) else (spline,) if spline is not None else ()
    parts = tuple(replace(part,
        start_body=paths.remap_body_reference(part.start_body),
        end_body=paths.remap_body_reference(part.end_body))
        for part in build.fit_parts if part.kind == "twist")
    independent = {}
    constraints = {}
    blended = {}
    body_paths = {path for _, path in paths.body_paths}
    for control in fk.controls:
        if control.driven_joint in body_paths:
            independent[control.driven_joint] = (
                control.source_override_path or control.sub_control_path
                or control.control_path) + ".worldMatrix[0]"
            constraints[control.driven_joint] = control.constraint_name
    for limb in limbs:
        for side in limb.blend.sides:
            for joint in side.joints:
                blended[joint.body_joint] = (
                    joint.fk_driver + ".worldMatrix[0]",
                    joint.ik_driver + ".worldMatrix[0]",
                    limb.blend.settings_path + "." + side.attribute,
                    joint.constraint_name)
    for spline in spline_plans:
        count = len(spline.body_joints)
        for index in range(1, count):
            blended[spline.body_joints[index]] = (
                spline.joints[index].path + ".worldMatrix[0]",
                spline.ik_outputs[index] + ".worldMatrix[0]",
                spline.mode_weight,
                spline.node_name(f"AdvPy_SplineOrient{index}"))
    for path in blended:
        independent.pop(path, None)
        constraints.pop(path, None)
    inputs = plan_standard_fit_part_rotation_inputs(parts,
        independent_world_matrices=independent,
        independent_body_constraints=constraints,
        blended_world_matrices=blended,
        semantic_parent_by_body={paths.remap_body_reference(spec.path):
            paths.remap_body_reference(spec.parent_path)
            for spec in build.specs if spec.parent_path is not None})
    # The original XformInverter receives FKX/parent blend world matrices.
    # Parenting references beneath a Bendy-driven Body introduces a loop
    # between adjacent segments, even if the projected joint source is independent.
    inputs = host.create_source_part_twist_references(inputs, independent, blended)
    sources = PrepareFitPartTwistSources(host).apply(inputs)
    bendy_parts = {name for chain in bendy_chains for name in chain.part_names}
    ordinary_parts = tuple(part for part in parts if part.name not in bendy_parts)
    ordinary_starts = {part.start_body for part in ordinary_parts}
    steps = BuildFitPartTwistDrivers(host).apply(ordinary_parts,
        tuple(source for source in sources if source.start_body in ordinary_starts))
    # Body output already contains this source rig's FK/IK scale selection.
    # Reuse that output for compensated Parts; OPM Parts inherit the parent.
    inbetween_driven = {part.body_part_name for segment in inbetween_segments
                        for part in segment.body.parts}
    scale_parts = tuple(part for part in build.fit_parts if part.name not in inbetween_driven)
    scale_plan = BuildFitPartScaleDrivers(host).apply(scale_parts,
        resolved_segment_scale_plugs={part.start_body_name:
            paths.remap_body_reference(part.start_body) + ".scale"
            for part in build.fit_parts})
    if bendy_chains:
        if any(chain.source_deform_matrix for chain in bendy_chains):
            from adv_py.core.source_spline_bendy_scale import plan_source_spline_bendy_scales
            scale_specs=plan_source_spline_bendy_scales(bendy_chains,fk,spline_plans)
            host.create_source_spline_bendy_scales(scale_specs)
            scale_by_body={spec.body:spec for spec in scale_specs}
            bendy_chains=tuple(replace(chain,source_scale_plugs=scale_by_body[chain.start_body].outputs)
                              if chain.start_body in scale_by_body else chain for chain in bendy_chains)
        world_sources = {body: FitBendyWorldSource(matrix)
                         for body, matrix in independent.items()}
        world_sources.update({body: FitBendyWorldSource(fk_matrix, ik_matrix, mode)
            for body, (fk_matrix, ik_matrix, mode, _) in blended.items()})
        for endpoint in fk.endpoints:
            world_sources[endpoint.driven_joint] = FitBendyWorldSource(
                endpoint.path + ".worldMatrix[0]")
        follows = plan_fit_bendy_follow(bendy_chains, None,
            resolved_world_sources=world_sources,
            untwist_plugs={source.start_body: source.down_twist_plug for source in sources},
            up_twist_plugs={source.start_body: source.up_twist_plug for source in sources
                            if source.up_twist_plug})
        BuildFitBendyGuides(host).apply(bendy_chains, follows=follows)
        BuildFitBendyDeform(host).apply(bendy_chains)
    return steps, scale_plan, bendy_chains
