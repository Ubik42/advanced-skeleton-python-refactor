"""Resolve a source Fit spline into the shared variable-length spline graph."""
from __future__ import annotations

from dataclasses import replace

from .body_spline import plan_body_spline_fk_chain
from .spline_names import scope_spline_plan,remap_spline_value
from .body_limb_controls import BodyLimbFkControlPlan
from .fit_ik import fit_joint_ik_info
from .fit_settings import FitSkeletonValidationError
from .joint_labels import JointLabel


def plan_source_body_splines(body, hierarchy, labels, fk, options, metadata=()):
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
    resolved=[]
    used=set()
    for info in found:
        for side in ('M','R','L'):
            source=tuple(by_name.get(nodes[path].short_name.rsplit(':',1)[-1]+'_'+side)
                         for path in info.joints)
            if source[0] is None:
                continue
            if any(joint is None for joint in source):
                raise FitSkeletonValidationError('来源 Spline 缺少对应侧完整骨链：'+info.name+'_'+side)
            deform={joint.path for joint in source[1:]}
            if used & deform:
                raise FitSkeletonValidationError('来源 Spline 变形链重叠：'+info.name+'_'+side)
            used.update(deform)
            resolved.append((info,side,source))
    if found and not resolved:
        raise FitSkeletonValidationError('来源 Spline 没有实际 Body 骨链')
    plans=[]
    for info,side,source in resolved:
        system='' if len(resolved)==1 and side=='M' else info.name+'_'+side
        generated_sources={joint.path:joint.source_joint for plan in plans for joint in plan.joints}
        fk,spline=_plan_source_chain(fk,source,info,options,metadata,system,generated_sources)
        plans.append(spline)
    return fk,tuple(plans)


def plan_source_body_spline(body,hierarchy,labels,fk,options,metadata=()):
    fk,plans=plan_source_body_splines(body,hierarchy,labels,fk,options,metadata)
    if len(plans)>1:
        raise FitSkeletonValidationError('调用方必须接收全部来源 Spline 系统')
    return fk,plans[0] if plans else None


def _plan_source_chain(fk,source,info,options,metadata,system,generated_sources):
    by_driver = {}
    for control in fk.controls:
        by_driver.setdefault(generated_sources.get(control.driven_joint,control.driven_joint),control)
    if any(joint.path not in by_driver for joint in source):
        raise FitSkeletonValidationError("来源 Spline 缺少完整的 FK 来源控制")
    end = by_driver[source[-1].path]
    chain_paths = {joint.path for joint in source}
    descendant_prefixes = tuple(path + "|" for path in
        (end.control_path, end.source_override_path) if path is not None)
    selected = tuple(replace(control,driven_joint=generated_sources.get(control.driven_joint,control.driven_joint))
                     for control in fk.controls
                     if generated_sources.get(control.driven_joint,control.driven_joint) in chain_paths
                     or control.parent_path.startswith(descendant_prefixes))
    # Preserve the ordinary Root/pelvis control, and add the original
    # independent base FK layer for spline deformation.
    controls = BodyLimbFkControlPlan(fk.root_path,
        fk.root_path.rsplit("|", 1)[-1], selected)
    updated, spline = plan_body_spline_fk_chain(source, controls,
        use_offset_parent_matrix=options.use_offset_parent_matrix,
        build_options=options, source_control_count=info.control_count)
    original_start=by_driver[source[0].path]
    updated=replace(updated,controls=tuple(replace(control,driven_joint=original_start.driven_joint)
        if control.control_name==original_start.control_name else control for control in updated.controls))
    start_metadata = next((item for item in metadata if item.joint==info.start), None)
    spline = replace(spline, source_ik_local=(start_metadata is not None
                     and start_metadata.ik_local_mode is not None))
    if system:
        updated=remap_spline_value(updated,system)
        spline=scope_spline_plan(spline,system)
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
