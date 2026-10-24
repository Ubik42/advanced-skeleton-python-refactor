"""Source asFollowLevels inputs and independent Spline endpoint hierarchy."""
from dataclasses import replace

from .fit_settings import FitSkeletonValidationError


def configure_source_spline_follow(plan, body, fk, global_control, *,
                                    root_control_path=None, root_follow_path=None,
                                    hierarchy=None, instances=()):
    if plan.system_name:
        from .spline_names import scope_spline_plan,remap_spline_value
        result=configure_source_spline_follow(scope_spline_plan(plan,''),body,
            remap_spline_value(fk,plan.system_name,canonical=True),global_control,
            root_control_path=root_control_path,root_follow_path=root_follow_path,
            hierarchy=hierarchy,instances=instances)
        return scope_spline_plan(result,plan.system_name)
    by_path = {joint.path: joint for joint in body.joints}
    root_control = next(control for control in fk.controls
                        if control.driven_joint == body.root)
    root_source = root_control_path or root_control.source_override_path or root_control.control_path
    start = by_path[plan.body_joints[0]]
    # MEL 81467 asks for the physical Body parent. Body planning may carry
    # semantic parents without the inserted Part receivers (fit_part.py).
    # The final DAG path retains both kinds of Part, even when the snapshot
    # does not include their rows. Root starts use RootX; direct Root children
    # use LegLockConstrained, exactly as the native constructor does.
    physical_parent = start.path.rsplit('|', 1)[0]
    if physical_parent == body.root:
        source = root_follow_path or root_source
    elif physical_parent.startswith(body.root + '|'):
        source = physical_parent
    else:
        source = root_source
    targets = [('MainExtra'+str(index),path,0.) for index,path in
               reversed(tuple(enumerate(global_control.extra_control_paths,1)))]
    targets += [('Main',global_control.control_path,10.),('Root',root_source,10.)]
    parent = start.parent_path
    # Follow levels query Fit rather than the physical Body parent. In
    # particular, inserted Body Parts never become user follow attributes.
    if hierarchy is not None:
        from .source_fit_identity import source_fit_reference, source_fit_build_name
        fit_path = source_fit_reference(start.name, instances)
        nodes = {node.path: node for node in hierarchy.joints}
        if fit_path is None or fit_path not in nodes:
            raise FitSkeletonValidationError('来源 Spline Follow 缺少实际 Fit 起点')
        chest_level = any(component.rsplit(':', 1)[-1] == 'Chest'
                          for component in fit_path.split('|')[:-1])
        # asAdvJointIKInfo strips NonSymmetry before listRelatives on the
        # start, so the additional parent level uses the unsuffixed Fit.
        build_name = source_fit_build_name(nodes[fit_path].short_name)
        canonical = tuple(node for node in hierarchy.joints
                          if node.short_name.rsplit(':', 1)[-1] == build_name)
        if len(canonical) != 1:
            raise FitSkeletonValidationError('来源 Spline Follow 无后缀 Fit 起点不唯一')
        fit_parent = nodes.get(canonical[0].dag_parent)
        parent_name = fit_parent.short_name.rsplit(':', 1)[-1] if fit_parent else None
    else:
        chest = next((joint.path for joint in body.joints if joint.name=='Chest_M'),None)
        chest_level = bool(chest and start.path.startswith(chest+'|'))
        # Legacy callers lack a Fit snapshot; only bypass actual Part tokens.
        import re
        while parent and re.search(r'Part[0-9]', parent.rsplit('|', 1)[-1]):
            parent = parent.rsplit('|', 1)[0]
        parent_name = by_path[parent].name.rsplit('_', 1)[0] if parent in by_path else None
    by_name = {joint.name.rsplit(':', 1)[-1]: joint.path for joint in body.joints}
    chest = by_name.get('Chest_M')
    if chest_level and chest:
        targets.append(('Chest',chest,10.))
    if parent_name and parent_name not in ('Root', 'Chest'):
        side = start.name.rsplit('_', 1)[-1]
        parent_target = by_name.get(parent_name + '_' + side) or by_name.get(parent_name + '_M')
        if parent_target is not None:
            targets.append((parent_name,parent_target,10.))
    # asFollowLevels initializes only the last Spline-specific level to 10;
    # Spline creation explicitly overrides followRoot to 10 afterwards.
    targets = tuple((label,path,10. if label in ('Main','Root') or
                     index==len(targets)-1 else 0.)
                    for index,(label,path,_) in enumerate(targets))
    if len({label for label,_,_ in targets})!=len(targets):
        raise FitSkeletonValidationError('来源 Spline Follow 层名称重复')
    result = replace(plan,source_follow_parent=source,source_follow_targets=targets,source_native_follow=True)
    controls = tuple(result.target_parent(index)+
                     f'|AdvPy_SplineIK{index}Offset|AdvPy_SplineIK{index}Extra|AdvPy_SplineIK{index}'
                     for index in range(len(result.targets)))
    subs = tuple(control+f'|AdvPy_SplineIK{index}Sub'
                 for index,control in enumerate(controls)) if result.sub_targets else ()
    return replace(result,targets=controls,sub_targets=subs)
