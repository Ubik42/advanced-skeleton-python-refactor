"""Connect source FK, RP and Spline Inbetween through the shared Part stages."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.body_limb_mechanisms import BodyLimbMechanismRole
from adv_py.core.fit_inbetween_ik_parts import plan_inbetween_ik_parts
from adv_py.core.fit_inbetween_ik_solver import plan_inbetween_ik_solver
from adv_py.core.fit_inbetween_ik_rebase import (
    rebase_inbetween_ik_reference, rebase_inbetween_ik_mechanisms,
)
from .fit_inbetween_ik_solver_mapping import (
    InbetweenIkSolverMapping, InbetweenIkSolverRequest,
)
from .fit_inbetween_limb_segment import BuildInbetweenLimbSegments
from .fit_inbetween_limb_mapping import (
    InbetweenLimbBinding, plan_generic_inbetween_fk_bindings,
)
from .fit_inbetween_fk_segment import BuildInbetweenFkSegment
from .fit_inbetween_untwister import BuildInbetweenUnTwister


def build_source_body_inbetween(host, build, part_result, fk, limbs, spline, *,
                                source_untwister_receiver=True):
    if part_result is None:
        return fk, limbs, (), InbetweenIkSolverMapping(())
    paths = part_result.final_paths
    from adv_py.core.fit_part import rebase_plan_paths_after_parts
    parts = rebase_plan_paths_after_parts(
        tuple(part for part in build.fit_parts if part.kind == "inbetween"), paths)
    grouped = {}
    for part in parts:
        grouped.setdefault(part.start_body, []).append(part)
    by_fk_driver = {control.driven_joint: control for control in fk.controls}
    ik_bindings = []
    handled = set()
    for limb in limbs:
        for side in limb.blend.sides:
            by_body = {joint.body_joint: joint for joint in side.joints}
            for before, chain in grouped.items():
                first = chain[0]
                start = paths.remap_body_reference(before)
                end = paths.remap_body_reference(first.end_body)
                if start not in by_body:
                    continue
                if end not in by_body:
                    raise ValueError("来源 Inbetween 末端不在同一 RP 链")
                start_driver, end_driver = by_body[start], by_body[end]
                start_control = by_fk_driver.get(start_driver.fk_driver)
                end_control = by_fk_driver.get(end_driver.fk_driver)
                if start_control is None:
                    raise ValueError("来源 RP Inbetween 缺少 FK 起点")
                ik_bindings.append(_source_ik_binding(
                    tuple(chain), fk, start_control, end_control,
                    start_driver.ik_driver, end_driver.ik_driver,
                    side.reverse_name + ".outputX",
                    limb.blend.settings_path + "." + side.attribute))
                handled.add(before)
    for spline in (spline if isinstance(spline,tuple) else (spline,) if spline is not None else ()):
        for index, (start_body, end_body) in enumerate(zip(
                spline.body_joints, spline.body_joints[1:])):
            for before, chain in grouped.items():
                first = chain[0]
                if paths.remap_body_reference(before) != start_body:
                    continue
                if paths.remap_body_reference(first.end_body) != end_body:
                    raise ValueError("来源 Spline Inbetween 缺少相邻末端")
                start_control = by_fk_driver.get(spline.joints[index].path)
                root_start=index==0 and start_body==part_result.body.root
                if root_start:
                    start_control=by_fk_driver.get(start_body)
                end_control = by_fk_driver.get(spline.joints[index + 1].path)
                if start_control is None:
                    raise ValueError("来源 Spline Inbetween 缺少 FK 起点")
                binding = _source_ik_binding(tuple(chain), fk, start_control, end_control,
                    spline.ik_outputs[index], spline.ik_outputs[index + 1],
                    spline.node_name("AdvPy_SplineReverse.outputX"), spline.mode_weight,
                    spline_root_path=spline.root_path)
                if index == 0 and spline.fk_root_point_from_receiver and not root_start:
                    binding = replace(binding,
                        start_fk_point_constraint_name=spline.node_name("AdvPy_SplineFKRootPoint"))
                ik_bindings.append(binding)
                handled.add(before)
    requests = []
    pending = {(binding.start_ik_driver, binding.end_ik_driver): binding
               for binding in ik_bindings if binding.spline_root_path is None}
    if len(pending) != sum(binding.spline_root_path is None for binding in ik_bindings):
        raise ValueError("来源 Inbetween IK 骨段重复登记")
    for limb in limbs:
        for spec in limb.ik.limbs:
            chain = tuple(joint.path for joint in limb.mechanisms.joints
                if joint.role is BodyLimbMechanismRole.IK and joint.side is spec.side
                and joint.source_joint.rsplit('|',1)[-1].rsplit('_',1)[0] in limb.joint_names)
            segments = tuple(plan_inbetween_ik_parts(binding.parts,
                             start_ik_driver=start, end_ik_driver=end)
                for start, end in zip(chain, chain[1:])
                if (binding := pending.pop((start, end), None)) is not None)
            if segments:
                solver = plan_inbetween_ik_solver(chain, segments,
                    handle_name=spec.handle_name,
                    effector_name=spec.handle_name.replace("Handle", "Effector"),
                    solver_name="ikRPsolver", handle_parent_path=(
                        next(side.final_handle_parent_path for side in limb.foot.sides if side.side is spec.side)
                        if limb.foot is not None else spec.wrist_sub_path or spec.wrist_control_path
                        if spec.source_aligned_graph else spec.wrist_control_path),
                    pole_control_path=spec.pole_control_path,
                    pole_constraint_name=spec.pole_constraint_name)
                requests.append(InbetweenIkSolverRequest(solver, segments))
        if limb.foot is not None:
            for foot in limb.foot.sides:
                sc_handles=[]
                if foot.hybrid is not None:
                    hybrid=foot.hybrid
                    sc_handles.append((hybrid.initial_handle_name,hybrid.initial_effector_name,
                        (*(hybrid.initial_solver_joint_list or (hybrid.initial_start_driver_path,)),
                         hybrid.initial_end_driver_path),hybrid.initial_handle_parent_path))
                    sc_handles.extend((step.handle_name,step.effector_name,
                        (*(step.solver_joint_list or (step.start_driver_path,)),step.end_driver_path),
                        step.handle_parent_path) for step in hybrid.segments)
                else:
                    sc_handles.append(
                        (foot.toe_handle_name,foot.toe_effector_name,
                         (*(foot.toe_solver_joint_list or (foot.toe_handle_start_path,)),foot.toe_driver_path),
                         foot.toe_handle_parent_path))
                    if foot.toe_end_driver_path:
                        sc_handles.append(
                        (foot.toe_end_handle_name,foot.toe_end_effector_name,
                         (*(foot.toe_end_solver_joint_list or (foot.toe_driver_path,)),foot.toe_end_driver_path),
                         foot.toe_end_handle_control_path))
                    if foot.qtoes_driver_path:
                        sc_handles.append((foot.qtoes_handle_name,foot.qtoes_effector_name,
                            (*(foot.qtoes_solver_joint_list or (foot.ankle_driver_path,)),foot.qtoes_driver_path),
                            foot.qtoes_handle_parent_path))
                    sc_handles.extend((step.handle_name,step.effector_name,
                        (*step.solver_joint_list,step.end_driver_path),step.parent_path)
                        for step in foot.intermediate_handles)
                for handle,effector,chain,parent in sc_handles:
                    segments=tuple(plan_inbetween_ik_parts(binding.parts,
                        start_ik_driver=start,end_ik_driver=end)
                        for start,end in zip(chain,chain[1:])
                        if (binding:=pending.pop((start,end),None)) is not None)
                    if segments:
                        solver=plan_inbetween_ik_solver(chain,segments,handle_name=handle,
                            effector_name=effector,solver_name='ikSCsolver',handle_parent_path=parent,
                            pole_control_path=None,pole_constraint_name=None)
                        requests.append(InbetweenIkSolverRequest(solver,segments))
    if pending:
        raise ValueError("来源 Inbetween 骨段没有对应的 RP／脚趾 SC 求解父链")
    mapping = InbetweenIkSolverMapping(tuple(requests))
    ik_built = (BuildInbetweenLimbSegments(host).apply(tuple(ik_bindings), None,
        solver_mapping=mapping,
        sub_controllers=build.build_options.sub_controllers,
        extra_controllers=build.build_options.extra_controllers)
        if ik_bindings else None)
    bindings = plan_generic_inbetween_fk_bindings(parts, fk, (),
        final_paths=paths, handled_start_paths=frozenset(handled))
    untwister_sources = {item.joint for item in build.symmetry.source.metadata
                        if item.untwister}
    segments = list(ik_built.segments) if ik_built is not None else []
    untwisters = []
    for binding, segment in zip(ik_bindings, segments):
        if binding.parts[0].source_joint in untwister_sources:
            if (binding.end_fk_control_path is None
                    or binding.downstream_fk_offset_path is None):
                raise ValueError("来源 IK Inbetween UnTwister 缺少下游 FK 控制")
            untwisters.append((binding, segment))
    rewired = {segment.rewire.start_fk_constraint_name:
        segment.fk.anchor.fk_offset_path + "|" + segment.fk.anchor.fkx_name
        for segment in segments}
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
            untwisters.append((binding, segment))
        rewired[binding.start_fk_constraint_name] = (
            segment.fk.anchor.fk_offset_path + "|" + segment.fk.anchor.fkx_name)
        segments.append(segment)
    if rewired:
        fk = replace(fk, controls=tuple(replace(control,
            source_override_path=rewired.get(control.constraint_name, control.source_override_path),
            source_override_joint=(False if control.constraint_name in rewired
                                   else control.source_override_joint))
            for control in fk.controls))
    # All Part anchors must exist before resolving the downstream FKX. A
    # downstream joint can itself start another Inbetween segment.
    for binding, segment in untwisters:
        receiver = None
        if source_untwister_receiver:
            control = next(item for item in fk.controls
                           if item.control_path == binding.end_fk_control_path)
            receiver = (control.source_override_path or control.sub_control_path
                        or control.control_path)
        BuildInbetweenUnTwister(host).apply(binding.parts,
            tuple(item.constraint_name for item in segment.body.parts),
            end_fk_control_path=binding.end_fk_control_path,
            end_fk_offset_path=binding.downstream_fk_offset_path,
            end_fk_receiver_path=receiver)
    solvers = tuple(request.plan for request in mapping.requests)
    if solvers:
        fk = rebase_inbetween_ik_reference(fk, solvers)
        updated = []
        by_handle = {solver.handle_name: solver for solver in solvers}
        for limb in limbs:
            rebased = rebase_inbetween_ik_reference(limb, solvers)
            ik = replace(rebased.ik, limbs=tuple(replace(spec,
                solver_joint_list=by_handle[spec.handle_name].solved_joint_list)
                if spec.handle_name in by_handle else spec for spec in rebased.ik.limbs))
            foot=rebased.foot
            if foot is not None:
                foot_rows=[]
                def solved(handle,old):
                    return by_handle[handle].solved_joint_list if handle in by_handle else old
                for side in foot.sides:
                    hybrid=side.hybrid
                    if hybrid:
                        hybrid=replace(hybrid,initial_solver_joint_list=solved(
                            hybrid.initial_handle_name,hybrid.initial_solver_joint_list),
                            segments=tuple(replace(step,solver_joint_list=solved(
                                step.handle_name,step.solver_joint_list)) for step in hybrid.segments))
                    foot_rows.append(replace(side,
                        toe_solver_joint_list=solved(side.toe_handle_name,side.toe_solver_joint_list),
                        toe_end_solver_joint_list=solved(side.toe_end_handle_name,side.toe_end_solver_joint_list),
                        qtoes_solver_joint_list=solved(side.qtoes_handle_name,side.qtoes_solver_joint_list),
                        intermediate_handles=tuple(replace(step,solver_joint_list=solved(
                            step.handle_name,step.solver_joint_list)) for step in side.intermediate_handles),
                        hybrid=hybrid))
                foot=replace(foot,sides=tuple(foot_rows))
            updated.append(replace(rebased, ik=ik,foot=foot,
                mechanisms=rebase_inbetween_ik_mechanisms(limb.mechanisms, solvers)))
        limbs = tuple(updated)
    return fk, limbs, tuple(segments), mapping


def _source_ik_binding(parts, fk, start_control, end_control, start_ik, end_ik,
                       fk_weight, ik_weight, *, spline_root_path=None):
    first = parts[0]
    return InbetweenLimbBinding(tuple(sorted(parts, key=lambda part: part.index)),
        start_control.offset_path, start_control.control_path, fk.root_path,
        start_control.driven_joint, start_control.constraint_name,
        end_control.offset_path if end_control is not None else None,
        end_control.control_path if end_control is not None else None,
        start_ik, end_ik, fk_weight, ik_weight, first.rotation_order,
        start_control.radius * .2, spline_root_path=spline_root_path,
        start_fk_source_path=(start_control.source_override_path
                              or start_control.sub_control_path or start_control.control_path),
        start_fk_point_constraint_name=start_control.translation_constraint_name)
