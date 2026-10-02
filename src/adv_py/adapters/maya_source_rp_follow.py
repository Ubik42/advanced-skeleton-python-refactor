"""Construct and retain original default RP follow graphs."""
from dataclasses import asdict
from adv_py.core.source_rp_follow import plan_source_rp_follows, SourceRpFollowPlan
from adv_py.core.body_fit_follow_spaces import BodyFitFollowSpacesSpec, BodyFitFollowSpaceTarget, BodyFitFollowSpacesState
from adv_py.core.body_leg_pole_aim import BodyLegPoleAimSpec
from adv_py.core.fit_symmetry import FitBuildSide
from adv_py.core.character_registry import canonical, safe_json, exact, CharacterRegistryError

MARKER='advPySourceRpFollow'


def create(host,body,limbs,global_control,root,*,leg_aim=()):
    host._require_transaction()
    c=host._cmds
    plans=plan_source_rp_follows(body,limbs,global_control,root,leg_aim=leg_aim)
    for plan in plans:
        swivel=plan.control+'.swivel'
        if not c.objExists(swivel):
            c.addAttr(plan.control,longName='swivel',attributeType='double',defaultValue=0.,keyable=True)
            c.connectAttr(swivel,plan.handle_twist)
        if plan.pole_aim:host.create_body_leg_pole_aim(plan.pole_aim)
        states=[]
        for spec in plan.spaces:
            state=host.preflight_body_fit_follow_spaces(spec)
            host.create_body_fit_follow_spaces(spec,state)
            if not host.capture_body_fit_follow_spaces(spec,state):
                raise CharacterRegistryError('来源 RP 默认 Follow 构建读回不一致')
            states.append(state)
        c.addAttr(plan.control,longName=MARKER,dataType='string')
        c.setAttr(plan.control+'.'+MARKER,canonical(dict(plan=asdict(plan),states=[asdict(s) for s in states])),type='string',lock=True)
    host._transaction_changed=True
    return plans


def decode(text):
    from adv_py.core.character_registry import path, identifier, vector, finite
    raw=exact(safe_json(text),('plan','states'))
    p=exact(raw['plan'],('control','pole','handle_twist','spaces','pole_aim'))
    spaces=[]
    for row in p['spaces']:
        exact(row,('source_body','fk_control','fk_offset','offset_parent','targets','blend_node','output_node'))
        targets=[]
        for t in row['targets']:
            exact(t,('label','source','weight','matrix_node','weight_node'))
            targets.append(BodyFitFollowSpaceTarget(identifier(t['label']),path(t['source']),finite(t['weight']),identifier(t['matrix_node']),identifier(t['weight_node'])))
        spaces.append(BodyFitFollowSpacesSpec(*(path(row[k]) for k in ('source_body','fk_control','fk_offset','offset_parent')),tuple(targets),identifier(row['blend_node']),identifier(row['output_node'])))
    states=[]
    for s in raw['states']:
        exact(s,('offset_world','parent_world','target_worlds','opm_source','opm_value','inherits_transform'))
        if type(s['inherits_transform']) is not bool:raise CharacterRegistryError('RP Follow 继承标记无效')
        states.append(BodyFitFollowSpacesState(vector(s['offset_world'],16),vector(s['parent_world'],16),tuple(vector(m,16) for m in s['target_worlds']),s['opm_source'],vector(s['opm_value'],16),s['inherits_transform']))
    if len(states)!=len(spaces) or any(len(s.targets)!=len(v.target_worlds) for s,v in zip(spaces,states)):
        raise CharacterRegistryError('RP Follow 目标与绑定状态不一致')
    aim=None
    if p['pole_aim']:
        from dataclasses import fields
        a=dict(p['pole_aim'])
        a.setdefault('aligned_orientation_source',None)
        a=exact(a,(f.name for f in fields(BodyLegPoleAimSpec)))
        aim=BodyLegPoleAimSpec(**{**a,'side':FitBuildSide(a['side']),'pole_position':vector(a['pole_position'],3)})
    plan=SourceRpFollowPlan(path(p['control']),path(p['pole']),p['handle_twist'],tuple(spaces),aim)
    if not plan.handle_twist.endswith('.twist'):raise CharacterRegistryError('RP Follow Handle 插口无效')
    return plan,tuple(states)


def audit(host,registration):
    c=host._cmds
    for binding in registration.source_limbs:
        plug=binding.ik_control+'.'+MARKER
        if not c.objExists(plug):continue # Existing source rigs predate default Follow.
        if not c.getAttr(plug,lock=True):raise CharacterRegistryError('RP Follow 记录已解锁')
        plan,states=decode(c.getAttr(plug))
        if (plan.control,plan.pole)!=(binding.ik_control,binding.pole_control):
            raise CharacterRegistryError('RP Follow 与角色来源登记不一致')
        if plan.pole_aim:host.capture_body_leg_pole_aim(plan.pole_aim,check_initial_pose=False)
        elif not c.isConnected(plan.control+'.swivel',plan.handle_twist,ignoreUnitConversion=True):
            raise CharacterRegistryError('RP swivel 接线变化')
        for spec,state in zip(plan.spaces,states):
            if not host.capture_body_fit_follow_spaces(spec,state,check_initial_pose=False):
                raise CharacterRegistryError('RP 默认 Follow 原生图变化：'+spec.fk_control)


def rebase_records(host,controls,rewrites):
    from adv_py.core.fit_part import FitPartFinalPaths,rebase_plan_paths_after_parts
    paths=FitPartFinalPaths((),(),tuple(rewrites))
    c=host._cmds
    for control in controls:
        plug=paths.remap_body_reference(control)+'.'+MARKER
        if not c.objExists(plug):continue
        plan,states=decode(c.getAttr(plug))
        plan=rebase_plan_paths_after_parts(plan,paths)
        states=rebase_plan_paths_after_parts(states,paths)
        c.setAttr(plug,lock=False)
        c.setAttr(plug,canonical(dict(plan=asdict(plan),states=[asdict(s) for s in states])),type='string',lock=True)
