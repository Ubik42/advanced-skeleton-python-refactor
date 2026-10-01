"""Source asFollowLevels inputs and independent Spline endpoint hierarchy."""
from dataclasses import replace

from .fit_settings import FitSkeletonValidationError


def configure_source_spline_follow(plan, body, fk, global_control):
    if plan.system_name:
        from .spline_names import scope_spline_plan,remap_spline_value
        result=configure_source_spline_follow(scope_spline_plan(plan,''),body,
            remap_spline_value(fk,plan.system_name,canonical=True),global_control)
        return scope_spline_plan(result,plan.system_name)
    by_path = {joint.path: joint for joint in body.joints}
    root_control = next(control for control in fk.controls
                        if control.driven_joint == body.root)
    root_source = root_control.source_override_path or root_control.control_path
    start = by_path[plan.body_joints[0]]
    parent = start.parent_path
    # Part receivers are not an additional Follow level in the MEL query.
    while parent in by_path and 'Part' in by_path[parent].name:
        parent = by_path[parent].parent_path
    source = parent if parent in by_path else root_source
    if parent == body.root:
        source = root_source
    targets = [('MainExtra'+str(index),path,0.) for index,path in
               reversed(tuple(enumerate(global_control.extra_control_paths,1)))]
    targets += [('Main',global_control.control_path,10.),('Root',root_source,10.)]
    chest = next((joint.path for joint in body.joints if joint.name=='Chest_M'),None)
    if chest and start.path.startswith(chest+'|'):
        targets.append(('Chest',chest,10.))
    if parent in by_path:
        label = by_path[parent].name.rsplit('_',1)[0]
        if label not in ('Root','Chest'):
            targets.append((label,parent,10.))
    # asFollowLevels initializes only the last Spline-specific level to 10;
    # Spline creation explicitly overrides followRoot to 10 afterwards.
    targets = tuple((label,path,10. if label in ('Main','Root') or
                     index==len(targets)-1 else 0.)
                    for index,(label,path,_) in enumerate(targets))
    if len({label for label,_,_ in targets})!=len(targets):
        raise FitSkeletonValidationError('来源 Spline Follow 层名称重复')
    result = replace(plan,source_follow_parent=source,source_follow_targets=targets)
    controls = tuple(result.target_parent(index)+
                     f'|AdvPy_SplineIK{index}Offset|AdvPy_SplineIK{index}Extra|AdvPy_SplineIK{index}'
                     for index in range(len(result.targets)))
    subs = tuple(control+f'|AdvPy_SplineIK{index}Sub'
                 for index,control in enumerate(controls)) if result.sub_targets else ()
    return replace(result,targets=controls,sub_targets=subs)
