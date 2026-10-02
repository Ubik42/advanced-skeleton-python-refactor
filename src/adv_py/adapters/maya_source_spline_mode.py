"""Original Advanced FKIK icon, parent receiver and 0–10 blend conversion."""
from dataclasses import replace

from adv_py.core.body_parent_constraint import plan_body_parent_constraint,audit_body_parent_constraint
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_adv_icons import create_adv_icon
from .maya_original_transform_channels import lock_original_transform_channels


def _follow_plan(host,plan):
    mode=plan.source_mode
    source=host.capture_parent_constraint_input(mode.parent_source,mode.frame,False)
    return plan_body_parent_constraint(replace(source,
        use_offset_parent_matrix=plan.use_offset_parent_matrix,
        skip_scale=not plan.use_offset_parent_matrix))


def create(host,plan, *, hybrid_unit=True):
    mode=plan.source_mode
    if mode is None:return
    host._require_transaction();host._transaction_changed=True
    c=host._cmds
    names=mode.node_names if hybrid_unit else tuple(
        name for name in mode.node_names if name!=mode.hybrid_visibility_unit)
    if any(host.find_name_collisions(name) for name in names):
        raise FitSkeletonValidationError('来源 Spline FKIK 控制器名称被占用：'+mode.name)
    frame=c.createNode('transform',name=mode.frame_name,
                       parent=mode.frame.rsplit('|',1)[0],skipSelect=True)
    follow=_follow_plan(host,plan)
    host.preflight_parent_constraint(follow);host.create_parent_constraint(follow)
    # MEL duplicates the icon at world origin, freezes its scale/Y rotation,
    # parents to the start Body to place it, then reparents to FKIK's receiver.
    holder=c.createNode('transform',name=mode.name+'IconHold',skipSelect=True)
    try:
        control=create_adv_icon(c,name=mode.name,parent=holder,template='FKIK_icon',
            radius=mode.radius,fallback_normal=(1.,0.,0.),axis_offset=(0.,90.,0.))
        c.parent(control,plan.body_joints[0],absolute=True)
    finally:
        c.delete(holder)
    control=(c.ls(mode.name,long=True) or [None])[0]
    if control is None:raise FitSkeletonValidationError('来源 Spline FKIK 图标缺失')
    direction=float(mode.side_sign)
    c.setAttr(control+'.translate',0.,0.,0.,type='double3')
    c.setAttr(control+'.translateX',mode.icon_scale*direction*5.)
    c.setAttr(control+'.translateZ',mode.icon_scale*direction*5.)
    fit=c.ls(mode.fit_start_joint,long=True,type='joint') or []
    if len(fit)!=1:raise FitSkeletonValidationError('来源 Spline FKIK 的 Fit 起点不唯一')
    if c.attributeQuery('fatWidth',node=fit[0],exists=True):
        from math import sqrt
        first=c.xform(control+'.cv[0]',q=True,worldSpace=True,t=True)
        last=c.xform(control+'.cv[5]',q=True,worldSpace=True,t=True)
        width=sqrt(sum((a-b)**2 for a,b in zip(first,last)))*direction
        c.setAttr(control+'.translateZ',float(c.getAttr(fit[0]+'.fat'))*
                  float(c.getAttr(fit[0]+'.fatWidth'))*direction+width/2.)
    if not mode.name.endswith('_M'):
        start=c.xform(plan.body_joints[0],q=True,ws=True,t=True)
        position=c.xform(control,q=True,ws=True,t=True)
        if (mode.name.endswith('_R') and position[0]>start[0]
                or mode.name.endswith('_L') and position[0]<start[0]):
            c.setAttr(control+'.translateZ',-float(c.getAttr(control+'.translateZ')))
    c.parent(control,mode.frame,absolute=True)
    lock_original_transform_channels(c,mode.control,True,True,True,True)
    c.addAttr(mode.control,longName='FKIKBlend',attributeType='double',
              minValue=0.,maxValue=10.,defaultValue=0.,keyable=True)
    for attribute,value in (('startJoint',mode.start_joint),('middleJoint',mode.middle_joint),('endJoint',mode.end_joint)):
        c.addAttr(mode.control,longName=attribute,dataType='string')
        c.setAttr(mode.control+'.'+attribute,value,type='string',lock=True)
    for unit in (mode.weight_unit,mode.visibility_unit)+((mode.hybrid_visibility_unit,) if hybrid_unit else ()):
        c.createNode('unitConversion',name=unit,skipSelect=True)
        c.setAttr(unit+'.conversionFactor',.1)
    for unit in (mode.weight_unit,mode.visibility_unit):
        c.connectAttr(plan.mode_plug,unit+'.input')
    c.createNode('setRange',name=mode.visibility_range,skipSelect=True)
    c.setAttr(mode.visibility_range+'.minX',10.)
    c.setAttr(mode.visibility_range+'.oldMaxX',10.)
    c.connectAttr(plan.mode_plug,mode.visibility_range+'.valueX')
    audit(host,plan,hybrid_unit=hybrid_unit)


def audit(host,plan, *, hybrid_unit=True):
    mode=plan.source_mode
    if mode is None:return
    c=host._cmds
    if ((c.listRelatives(mode.frame,parent=True,fullPath=True) or [])!=[mode.frame.rsplit('|',1)[0]]
            or (c.listRelatives(mode.control,parent=True,fullPath=True) or [])!=[mode.frame]):
        raise FitSkeletonValidationError('来源 Spline FKIK 父链改变')
    follow=_follow_plan(host,plan)
    state=host.capture_parent_constraint_state(follow)
    issues=audit_body_parent_constraint(follow,state)
    if issues:raise FitSkeletonValidationError('来源 Spline FKIK 父级驱动改变：'+repr(issues)
        +' expected='+repr(follow)+' actual='+repr(state))
    if (tuple(c.attributeQuery('FKIKBlend',node=mode.control,minimum=True))!=(0.,)
            or tuple(c.attributeQuery('FKIKBlend',node=mode.control,maximum=True))!=(10.,)):
        raise FitSkeletonValidationError('来源 Spline FKIK 用户范围必须为 0–10')
    for attribute,value in (('startJoint',mode.start_joint),('middleJoint',mode.middle_joint),('endJoint',mode.end_joint)):
        if c.getAttr(mode.control+'.'+attribute)!=value or not c.getAttr(mode.control+'.'+attribute,lock=True):
            raise FitSkeletonValidationError('来源 Spline FKIK 骨链标记改变：'+attribute)
    for unit in (mode.weight_unit,mode.visibility_unit)+((mode.hybrid_visibility_unit,) if hybrid_unit else ()):
        if c.nodeType(unit)!='unitConversion' or abs(c.getAttr(unit+'.conversionFactor')-.1)>1e-12:
            raise FitSkeletonValidationError('来源 Spline FKIK 权重转换改变：'+unit)
    edges=tuple((plan.mode_plug,unit+'.input') for unit in (mode.weight_unit,mode.visibility_unit))
    edges+=((plan.mode_plug,mode.visibility_range+'.valueX'),)
    if (c.nodeType(mode.visibility_range)!='setRange'
            or any(c.getAttr(mode.visibility_range+'.'+attribute)!=value
                   for attribute,value in (('minX',10.),('maxX',0.),('oldMinX',0.),('oldMaxX',10.)))
            or any(not c.isConnected(source,destination) for source,destination in edges)):
        raise FitSkeletonValidationError('来源 Spline FKIK 用户值或显示范围接线改变')
