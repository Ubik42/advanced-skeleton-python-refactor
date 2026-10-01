"""Original Spline automatic/manual FK, IK and Hybrid visibility routing."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.fit_settings import FitSkeletonValidationError


def normalize_layer_state(host,state,flag,output):
    """Accept only our exact flag × Spline visibility route."""
    c=host._cmds
    source=state.visibility_source
    if source is None or source==flag:
        return state
    node=source.rsplit('.',1)[0]
    shape=getattr(state,'shape_path',None)
    if shape is None:
        shapes=c.listRelatives(state.path,shapes=True,noIntermediate=True,fullPath=True) or []
        shape=shapes[0] if len(shapes)==1 else None
    expected=shape.rsplit('|',1)[-1]+'SplineVis' if shape else None
    if (node!=expected or source!=node+'.output' or c.nodeType(node)!='multDoubleLinear'
            or not c.isConnected(flag,node+'.input1')
            or not c.isConnected('AdvPy_SplineVisibility.'+output,node+'.input2')
            or not c.isConnected(source,shape+'.visibility')):
        return state
    return replace(state,visibility_source=flag)


def create(host,plan,fk):
    if plan.system_name:
        from .maya_spline_scope import spline_scope
        from adv_py.core.spline_names import remap_spline_value
        with spline_scope(host,plan) as local:
            return create(host,local,remap_spline_value(fk,plan.system_name,canonical=True))
    c = host._cmds
    settings = plan.settings
    for attr in ('autoVis','FKVis','IKVis'):
        c.addAttr(settings,longName=attr,attributeType='bool',defaultValue=True)
        c.setAttr(settings+'.'+attr,keyable=attr!='autoVis',channelBox=True)
    condition = c.createNode('condition',name='AdvPy_SplineVisibility',skipSelect=True)
    c.connectAttr(settings+'.autoVis',condition+'.firstTerm')
    c.connectAttr(settings+'.IKVis',condition+'.colorIfTrueR')
    c.connectAttr(settings+'.FKVis',condition+'.colorIfTrueG')
    c.connectAttr(settings+'.spineIkFk',condition+'.colorIfFalseR')
    c.connectAttr('AdvPy_SplineReverse.outputX',condition+'.colorIfFalseG')
    hidden = set(fk.hidden_controls)
    fk_by_path = {control.control_path:control for control in fk.controls}
    def route(control,source):
        for shape in c.listRelatives(control,shapes=True,fullPath=True,type='nurbsCurve') or []:
            destination = shape+'.visibility'
            previous = c.connectionInfo(destination,sourceFromDestination=True)
            if previous:
                gate = c.createNode('multDoubleLinear',name=shape.rsplit('|',1)[-1]+'SplineVis',skipSelect=True)
                c.disconnectAttr(previous,destination)
                c.connectAttr(previous,gate+'.input1')
                c.connectAttr(source,gate+'.input2')
                c.connectAttr(gate+'.output',destination)
            else:
                if c.getAttr(destination,lock=True):
                    c.setAttr(destination,lock=False)
                c.connectAttr(source,destination)
    for path in plan.fk_controls:
        if path in hidden:
            continue
        control = fk_by_path[path]
        for node in (path,control.sub_control_path,control.extra_path):
            if node is not None:
                route(node,condition+'.outColorG')
    for index,path in enumerate(plan.targets):
        for node in (path,plan.sub_targets[index] if plan.sub_targets else None,
                     plan.extra_targets[index] if plan.extra_targets else None):
            if node is not None:
                route(node,condition+'.outColorR')
    for path in plan.cv_controls:
        route(path,condition+'.outColorR')
    c.connectAttr(condition+'.outColorR',plan.curve+'.visibility')
    c.setAttr(plan.curve+'.overrideEnabled',True)
    c.setAttr(plan.curve+'.overrideDisplayType',1)
    if plan.source_hybrid_graph:
        hybrid = c.createNode('plusMinusAverage',name='AdvPy_SplineHybridVisibility',skipSelect=True)
        c.setAttr(hybrid+'.operation',3)
        c.connectAttr(condition+'.outColorR',hybrid+'.input1D[0]')
        c.connectAttr(settings+'.ikHybridVis',hybrid+'.input1D[1]')
        c.setAttr(hybrid+'.input1D[2]',-.5)
        for control in plan.hybrid_controls:
            for shape in c.listRelatives(control,shapes=True,fullPath=True) or []:
                c.disconnectAttr(settings+'.ikHybridVis',shape+'.visibility')
                c.connectAttr(hybrid+'.output1D',shape+'.visibility')


def audit(host,plan):
    c = host._cmds
    condition = 'AdvPy_SplineVisibility'
    if not c.objExists(condition) or c.nodeType(condition)!='condition':
        raise FitSkeletonValidationError('来源 Spline 显示条件图缺失')
    edges = tuple((plan.settings+'.'+attr,condition+'.'+destination)
        for attr,destination in (('autoVis','firstTerm'),('IKVis','colorIfTrueR'),
                                 ('FKVis','colorIfTrueG'),('spineIkFk','colorIfFalseR')))
    edges += (('AdvPy_SplineReverse.outputX',condition+'.colorIfFalseG'),
              (condition+'.outColorR',plan.curve+'.visibility'))
    if plan.source_hybrid_graph:
        node='AdvPy_SplineHybridVisibility'
        if (not c.objExists(node) or c.nodeType(node)!='plusMinusAverage'
                or c.getAttr(node+'.operation')!=3 or c.getAttr(node+'.input1D[2]')!=-.5):
            raise FitSkeletonValidationError('来源 Spline Hybrid 显示混合改变')
        edges += ((condition+'.outColorR',node+'.input1D[0]'),
                  (plan.settings+'.ikHybridVis',node+'.input1D[1]'))
    if c.getAttr(condition+'.operation')!=0 or c.getAttr(condition+'.secondTerm')!=0:
        raise FitSkeletonValidationError('来源 Spline 自动显示条件改变')
    if any(not c.isConnected(source,destination) for source,destination in edges):
        raise FitSkeletonValidationError('来源 Spline 显示关系改变')
