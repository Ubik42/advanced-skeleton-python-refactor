"""Connect source FK-only Inbetween segments using the shared Part stages."""
from __future__ import annotations

from dataclasses import replace

from .fit_inbetween_limb_mapping import plan_generic_inbetween_fk_bindings
from .fit_inbetween_fk_segment import BuildInbetweenFkSegment
from .fit_inbetween_untwister import BuildInbetweenUnTwister


def build_source_body_inbetween(host, build, part_result, fk, limbs, spline):
    if part_result is None:
        return fk, ()
    driven = {joint.body_joint for limb in limbs for side in limb.blend.sides
              for joint in side.joints}
    if spline is not None:
        driven.update(spline.body_joints)
    handled = frozenset(before for before, after in part_result.final_paths.body_rewrites
                        if after in driven)
    parts = tuple(part for part in build.fit_parts if part.kind == "inbetween")
    bindings = plan_generic_inbetween_fk_bindings(parts, fk, (),
        final_paths=part_result.final_paths, handled_start_paths=handled)
    untwister_sources = {item.joint for item in build.symmetry.source.metadata
                        if item.untwister}
    segments = []
    rewired = {}
    for binding in bindings:
        segment = BuildInbetweenFkSegment(host).apply(binding.parts,
            fk_offset_path=binding.fk_offset_path,
            fk_control_path=binding.fk_control_path,
            fk_system_path=binding.fk_system_path,
            start_fk_driver_path=binding.start_fk_driver_path,
            start_fk_constraint_name=binding.start_fk_constraint_name,
            start_fk_source_path=binding.start_fk_source_path,
            start_fk_point_constraint_name=binding.start_fk_point_constraint_name,
            downstream_fk_offset_path=binding.downstream_fk_offset_path,
            rotate_order=binding.rotate_order,
            part_control_radius=binding.part_control_radius,
            sub_controllers=build.build_options.sub_controllers,
            extra_controllers=build.build_options.extra_controllers)
        if binding.parts[0].source_joint in untwister_sources:
            if (binding.end_fk_control_path is None
                    or binding.downstream_fk_offset_path is None):
                raise ValueError("来源 Inbetween UnTwister 缺少下游 FK 控制")
            BuildInbetweenUnTwister(host).apply(binding.parts,
                tuple(item.constraint_name for item in segment.body.parts),
                end_fk_control_path=binding.end_fk_control_path,
                end_fk_offset_path=binding.downstream_fk_offset_path)
        rewired[binding.start_fk_constraint_name] = (
            segment.fk.anchor.fk_offset_path + "|" + segment.fk.anchor.fkx_name)
        segments.append(segment)
    if rewired:
        fk = replace(fk, controls=tuple(replace(control,
            source_override_path=rewired.get(control.constraint_name, control.source_override_path),
            source_override_joint=(False if control.constraint_name in rewired
                                   else control.source_override_joint))
            for control in fk.controls))
    return fk, tuple(segments)
