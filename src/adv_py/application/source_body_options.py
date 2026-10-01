"""Fit Wheel, CurveGuide and Tweaker stages for the shared source builder."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.body_fit_wheel import plan_body_fit_wheels
from adv_py.core.body_fit_curve_guide import plan_body_fit_curve_guides
from adv_py.core.fit_tweaker import plan_fit_tweakers
from .fit_tweaker import BuildFitTweakers
from .source_body_follow import source_fk_body_controls


def build_source_body_options(host, build, body, fk, limbs, spline,
                              global_control, part_result):
    controls = source_fk_body_controls(body, fk, limbs, spline)
    metadata = build.symmetry.source.metadata
    wheels = plan_body_fit_wheels(metadata, build.symmetry.instances, controls,
        scale_plug=global_control.scale_node_name+'.input1Y')
    curve_plan = plan_body_fit_curve_guides(metadata, build.symmetry.instances,
        build.specs, controls,
        final_paths=part_result.final_paths if part_result is not None else None)
    tweakers = None
    if build.build_options.use_offset_parent_matrix:
        tweakers = plan_fit_tweakers(build.symmetry.instances, metadata,
            build.fit_parts if part_result is not None else (),
            motion_system_path=global_control.root_path.rsplit('|',2)[0],
            global_control_path=global_control.control_path,
            body_profiles={spec.path:spec.deform_profile for spec in build.specs},
            final_paths=part_result.final_paths if part_result is not None else None)
        BuildFitTweakers(host).apply(tweakers)
    curves = (host.create_body_fit_curve_guides(curve_plan,
        main_control=global_control.control_path,
        fit_container=build.symmetry.source.hierarchy.container) if curve_plan else ())
    if wheels:
        # Use the actual generated FK drivers when handing off the rotation
        # receiver; the Body-identity view above is only for Fit target lookup.
        actual = {control.control_path:control for control in fk.controls}
        wheels = tuple(replace(wheel,control=actual[wheel.control.control_path])
                       for wheel in wheels)
        host.create_body_fit_wheels(wheels)
        receivers = {wheel.control.constraint_name:
            (wheel.control.sub_control_path or wheel.control.control_path)
            +'|AdvPy_WheelFKX'+wheel.control.control_name.removeprefix('AdvPy_')
            for wheel in wheels if wheel.control.source_override_path is None}
        fk = replace(fk,controls=tuple(replace(control,
            source_override_path=receivers[control.constraint_name])
            if control.constraint_name in receivers else control for control in fk.controls))
    return fk, wheels, curves, tweakers
