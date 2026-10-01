"""Use the original Fit follow stages with resolved source Body identities."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.body_limb_mechanisms import BodyLimbMechanismRole
from .body_fit_follow import BuildFitFollow
from .body_fit_named_follow import BuildFitNamedFollow
from .body_fit_follow_spaces import BuildFitFollowSpaces
from .body_fit_ik_follow import BuildFitIkFollow
from .body_fit_advanced_constraint import BuildFitAdvancedConstraints
from .body_fit_aim_at import BuildFitAimAt
from .body_fit_geo_attach import BuildFitGeoAttach
from .body_fit_proximity_pin import BuildFitProximityPin
from adv_py.core.body_fit_follow import plan_body_fit_follow
from adv_py.core.body_fit_named_follow import plan_body_fit_named_follow
from adv_py.core.body_fit_follow_spaces import plan_body_fit_follow_spaces
from adv_py.core.body_fit_ik_follow import plan_body_fit_ik_follow
from adv_py.core.body_fit_advanced_constraint import plan_body_fit_advanced_constraints
from adv_py.core.body_fit_aim_at import plan_body_fit_aim_at
from adv_py.core.body_fit_dependency import validate_fit_control_dependencies


def source_fk_body_controls(body, fk, limbs, spline):
    sources = {joint.path: joint.source_joint for limb in limbs
               for joint in limb.mechanisms.joints
               if joint.role is BodyLimbMechanismRole.FK}
    for spline in (spline if isinstance(spline,tuple) else (spline,) if spline is not None else ()):
        sources.update((joint.path,joint.source_joint) for joint in spline.joints
                       if joint.role is BodyLimbMechanismRole.FK)
    controls = []
    used = set()
    for control in fk.controls:
        source = sources.get(control.driven_joint, control.driven_joint)
        # Root already has its independent source control. Its added Spline
        # Base FK is a deformation receiver, not a second Fit metadata owner.
        if source in used:
            continue
        used.add(source)
        controls.append(replace(control, driven_joint=source))
    return tuple(controls)


def build_source_body_follow(host, metadata, body, fk, limbs, spline, global_control):
    controls = source_fk_body_controls(body, fk, limbs, spline)
    root = next(control for control in controls if control.driven_joint==body.root)
    driver_sources = tuple((joint.path,joint.source_joint) for limb in limbs
        for joint in limb.mechanisms.joints if joint.role is BodyLimbMechanismRole.IK)
    ik_controls = tuple(spec for limb in limbs for spec in limb.ik.limbs)
    named_plan = plan_body_fit_named_follow(metadata, controls, body.joints)
    spaces_plan = plan_body_fit_follow_spaces(metadata, controls, body.joints,
        main_path=global_control.control_path, root_path=root.control_path,
        main_extra_paths=global_control.extra_control_paths)
    body_by_control = {path:control.driven_joint for control in controls
                       for path in (control.control_path,control.source_override_path)
                       if path is not None}
    aim_plan = plan_body_fit_aim_at(metadata, controls, body.joints)
    validate_fit_control_dependencies(
        plan_body_fit_advanced_constraints(metadata, controls, body.joints),
        plan_body_fit_follow(metadata, controls, body.joints) +
        plan_body_fit_ik_follow(metadata, ik_controls, (), body.joints,
            spline=spline, driver_body_sources=driver_sources),
        tuple((spec.source_body, host.resolve_body_fit_named_follow_targets(spec))
              for spec in named_plan) + tuple((spec.source_body,
              tuple(body_by_control.get(target.source,target.source) for target in spec.targets))
              for spec in spaces_plan) + tuple((spec.source_body,(spec.target_body,))
              for spec in aim_plan))
    constraints = BuildFitAdvancedConstraints(host).apply(metadata, controls, body.joints)
    follows = BuildFitFollow(host).apply(metadata, controls, body.joints)
    named = BuildFitNamedFollow(host).apply(metadata, controls, body.joints)
    spaces = BuildFitFollowSpaces(host).apply(metadata, controls, body.joints,
        main_path=global_control.control_path, root_path=root.control_path,
        main_extra_paths=global_control.extra_control_paths)
    ik = BuildFitIkFollow(host).apply(metadata,
        ik_controls, (), body.joints,
        spline=spline, driver_body_sources=driver_sources)
    aim = BuildFitAimAt(host).apply(metadata, controls, body.joints)
    geometry = BuildFitGeoAttach(host).apply(metadata, controls, body.joints)
    proximity = BuildFitProximityPin(host).apply(metadata, controls, body.joints)
    return follows, named, spaces, ik, constraints, aim, geometry, proximity
