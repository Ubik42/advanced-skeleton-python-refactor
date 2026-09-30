"""Resolve a source Fit spline into the shared variable-length spline graph."""
from __future__ import annotations

from dataclasses import replace

from .body_spline import plan_body_spline_fk_chain
from .body_limb_controls import BodyLimbFkControlPlan
from .fit_ik import fit_joint_ik_info
from .fit_settings import FitSkeletonValidationError
from .joint_labels import JointLabel


def plan_source_body_spline(body, hierarchy, labels, fk, options):
    label_by_name = dict(labels)
    fit_labels = {node.path: (JointLabel.parse(label_by_name[name])
                             if name in label_by_name else None)
                  for node in hierarchy.joints
                  for name in (node.short_name.rsplit(":", 1)[-1],)}
    nodes = {node.path: node for node in hierarchy.joints}
    by_name = {joint.name: joint for joint in body.joints}
    found = []
    for node in hierarchy.joints:
        info = fit_joint_ik_info(hierarchy, fit_labels, node.path)
        if info is not None and info.start == node.path and info.solver == "ikSplineSolver":
            found.append(info)
    if not found:
        return fk, None
    if len(found) != 1:
        raise FitSkeletonValidationError("来源多组 Spline 的独立系统命名尚未接齐")
    info = found[0]
    source = tuple(by_name.get(nodes[path].short_name.rsplit(":", 1)[-1] + "_M")
                   for path in info.joints)
    if any(joint is None for joint in source):
        raise FitSkeletonValidationError("来源 Spline 的侧向系统尚未接齐")
    by_driver = {control.driven_joint: control for control in fk.controls}
    if any(joint.path not in by_driver for joint in source):
        raise FitSkeletonValidationError("来源 Spline 缺少完整的 FK 来源控制")
    end = by_driver[source[-1].path]
    chain_paths = {joint.path for joint in source}
    descendant_prefixes = tuple(path + "|" for path in
        (end.control_path, end.source_override_path) if path is not None)
    selected = tuple(control for control in fk.controls
                     if control.driven_joint in chain_paths
                     or control.parent_path.startswith(descendant_prefixes))
    # Preserve the ordinary Root/pelvis control, and add the original
    # independent base FK layer for spline deformation.
    controls = BodyLimbFkControlPlan(fk.root_path,
        fk.root_path.rsplit("|", 1)[-1], selected)
    updated, spline = plan_body_spline_fk_chain(source, controls,
        use_offset_parent_matrix=options.use_offset_parent_matrix,
        build_options=options)
    by_control = {control.control_name: control for control in updated.controls}
    merged = tuple(by_control.get(control.control_name, control)
                   for control in fk.controls)
    original_names = {control.control_name for control in fk.controls}
    additions = tuple(control for control in updated.controls
                      if control.control_name not in original_names)
    # A newly inserted base must exist before its child controls.
    merged = tuple(sorted(merged + additions,
                          key=lambda control: control.control_path.count("|")))
    changed = tuple((old.offset_path, by_control[old.control_name].offset_path)
                    for old in fk.controls if old.control_name in by_control
                    and old.offset_path != by_control[old.control_name].offset_path)
    def remap(path):
        if path is None:
            return None
        for before, after in sorted(changed, key=lambda pair: len(pair[0]), reverse=True):
            if path == before or path.startswith((before + "|", before + ".")):
                return after + path[len(before):]
        return path
    endpoints = tuple(replace(endpoint,
        path=remap(endpoint.path), parent_path=remap(endpoint.parent_path),
        follow_fk_matrix=remap(endpoint.follow_fk_matrix),
        follow_ik_matrix=remap(endpoint.follow_ik_matrix),
        follow_blend_plug=remap(endpoint.follow_blend_plug))
        for endpoint in fk.endpoints)
    hidden = tuple(remap(path) for path in fk.hidden_controls)
    if by_driver[source[0].path].control_path in fk.hidden_controls:
        hidden += tuple(control.control_path for control in additions)
    return replace(fk, controls=merged,
                   hidden_controls=hidden,
                   endpoints=endpoints), spline
