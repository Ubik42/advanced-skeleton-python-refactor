"""Original-style end-follow weights for middle Spline IK controls."""
from __future__ import annotations

from adv_py.core.fit_settings import FitSkeletonValidationError


def _follow_frame(c, plan, name, target):
    node = c.createNode('transform', name=name, parent=plan.mid_follow_parent if plan.source_ik_chain else plan.root_path,
                        skipSelect=True)
    node = (c.ls(node, long=True) or [node])[0]
    c.setAttr(node+'.inheritsTransform',bool(plan.source_ik_chain),lock=True)
    c.xform(node, worldSpace=True,
            matrix=c.xform(target, query=True, worldSpace=True, matrix=True))
    return node


def create(host, plan):
    c = host._cmds
    count = len(plan.targets)
    if count < 3 or not plan.source_curve_points and len(plan.body_joints) <= 2:
        raise FitSkeletonValidationError('Spline 中间跟随需要多段 IK 链')
    start = _follow_frame(c, plan, 'AdvPy_SplineFollowStart', plan.driver_targets[0])
    end = _follow_frame(c, plan, 'AdvPy_SplineFollowEnd', plan.driver_targets[-1])
    c.parentConstraint(plan.driver_targets[0], start, maintainOffset=False,
                       name='AdvPy_SplineFollowStartConstraint')
    c.parentConstraint(plan.driver_targets[-1], end, maintainOffset=False,
                       name='AdvPy_SplineFollowEndConstraint')
    c.createNode('setRange', name='AdvPy_SplineMidFlipAxis', skipSelect=True)
    for plug, value in (('minX', 2), ('maxX', 1), ('oldMaxX', 1)):
        c.setAttr('AdvPy_SplineMidFlipAxis.'+plug, value)
    c.connectAttr(plan.settings+'.noFlipAxis',
                  'AdvPy_SplineMidFlipAxis.valueX')
    for index, target in enumerate(plan.targets[1:-1], 1):
        offset = plan.offset_targets[index]
        default = 10.0*index/(count-1)
        c.addAttr(target, longName='followEnd', niceName='跟随末端',
                  attributeType='double', minValue=0., maxValue=10.,
                  defaultValue=default, keyable=True)
        weight = c.createNode('unitConversion',
                              name=f'AdvPy_SplineFollowWeight{index}',
                              skipSelect=True)
        c.setAttr(weight+'.conversionFactor', .1)
        c.connectAttr(target+'.followEnd', weight+'.input')
        reverse = c.createNode('reverse',
                               name=f'AdvPy_SplineFollowReverse{index}',
                               skipSelect=True)
        c.connectAttr(weight+'.output', reverse+'.inputX')
        node = c.parentConstraint(start, end, offset, maintainOffset=True,
                                  name=f'AdvPy_SplineFollowConstraint{index}')[0]
        aliases = c.parentConstraint(node, query=True, weightAliasList=True)
        if len(aliases) != 2:
            raise FitSkeletonValidationError('Spline 中间跟随约束目标不完整')
        c.connectAttr(reverse+'.outputX', node+'.'+aliases[0])
        c.connectAttr(weight+'.output', node+'.'+aliases[1])
        c.connectAttr('AdvPy_SplineMidFlipAxis.outValueX',
                      node+'.interpType')


def audit(host, plan):
    c = host._cmds
    if plan.isolated_mid_follow_graph:
        parent = plan.mid_follow_parent
        if ((c.listRelatives(parent, parent=True, fullPath=True) or [])
                != [plan.pelvis_control]
                or c.getAttr(parent+'.inheritsTransform')
                or not c.getAttr(parent+'.inheritsTransform', lock=True)):
            raise FitSkeletonValidationError('Spline 独立跟随层归属或缩放隔离失效')
        identity = (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
        if any(abs(a-b)>1e-8 for a,b in zip(c.getAttr(parent+'.matrix'), identity)):
            raise FitSkeletonValidationError('Spline 独立跟随层局部矩阵被修改')
        if any(not c.getAttr(parent+'.'+kind+axis, lock=True)
               for kind in ('translate','rotate','scale','shear')
               for axis in ('XYZ' if kind!='shear' else ('XY','XZ','YZ'))):
            raise FitSkeletonValidationError('Spline 独立跟随层变换未锁定')
    if plan.source_ik_chain and not c.isConnected(plan.scale_reference+'.worldMatrix[0]',plan.mid_follow_parent+'.offsetParentMatrix'):
        raise FitSkeletonValidationError('来源 Spline 中间跟随没有继承 Main 世界矩阵')
    frame_parent=plan.mid_follow_parent if plan.source_ik_chain else plan.root_path
    start = frame_parent+'|AdvPy_SplineFollowStart'
    end = frame_parent+'|AdvPy_SplineFollowEnd'
    edges = [(plan.settings+'.noFlipAxis',
              'AdvPy_SplineMidFlipAxis.valueX')]
    constants = {'AdvPy_SplineMidFlipAxis.minX': 2,
                 'AdvPy_SplineMidFlipAxis.maxX': 1,
                 'AdvPy_SplineMidFlipAxis.oldMaxX': 1}
    for frame, source, name in (
            (start, plan.driver_targets[0], 'AdvPy_SplineFollowStartConstraint'),
            (end, plan.driver_targets[-1], 'AdvPy_SplineFollowEndConstraint')):
        if bool(c.getAttr(frame+'.inheritsTransform'))!=bool(plan.source_ik_chain):
            raise FitSkeletonValidationError('Spline 跟随参考继承了机制层变换')
        targets = tuple(host._resolve_connected_node(p)
                        for p in c.parentConstraint(name, query=True,
                                                    targetList=True))
        if targets != (source,):
            raise FitSkeletonValidationError('Spline 跟随参考目标被替换')
        for axis in 'XYZ':
            edges.extend(((name+'.constraintTranslate'+axis,
                           frame+'.translate'+axis),
                          (name+'.constraintRotate'+axis,
                           frame+'.rotate'+axis)))
    count = len(plan.targets)
    for index, target in enumerate(plan.targets[1:-1], 1):
        if (not c.attributeQuery('followEnd', node=target, exists=True)
                or c.getAttr(target+'.followEnd', type=True)!='double'):
            raise FitSkeletonValidationError('Spline 中间跟随权重属性缺失')
        offset = plan.offset_targets[index]
        expected_parent = (plan.mid_follow_parent if plan.isolated_mid_follow_graph
                           else plan.pelvis_control)
        if (c.listRelatives(offset, parent=True, fullPath=True) or []) != [expected_parent]:
            raise FitSkeletonValidationError('Spline 中间控制器跟随父级被替换')
        weight = f'AdvPy_SplineFollowWeight{index}'
        reverse = f'AdvPy_SplineFollowReverse{index}'
        name = f'AdvPy_SplineFollowConstraint{index}'
        targets = tuple(host._resolve_connected_node(p)
                        for p in c.parentConstraint(name, query=True,
                                                    targetList=True))
        aliases = c.parentConstraint(name, query=True, weightAliasList=True)
        if targets != (start, end) or len(aliases)!=2:
            raise FitSkeletonValidationError('Spline 中间跟随约束目标被替换')
        constants[weight+'.conversionFactor'] = .1
        edges.extend(((target+'.followEnd',weight+'.input'),
                      (weight+'.output',reverse+'.inputX'),
                      (reverse+'.outputX',name+'.'+aliases[0]),
                      (weight+'.output',name+'.'+aliases[1]),
                      ('AdvPy_SplineMidFlipAxis.outValueX',
                       name+'.interpType')))
        for axis in 'XYZ':
            edges.extend(((name+'.constraintTranslate'+axis,
                           offset+'.translate'+axis),
                          (name+'.constraintRotate'+axis,
                           offset+'.rotate'+axis)))
    changed = [(plug, value) for plug, value in constants.items()
               if abs(c.getAttr(plug)-value)>1e-6]
    if changed:
        raise FitSkeletonValidationError('Spline 中间跟随常量被修改：'+repr(changed[:2]))
    bad = [(source, destination) for source, destination in edges
           if not c.isConnected(source, destination)]
    if bad:
        raise FitSkeletonValidationError('Spline 中间跟随图连接被替换：'+repr(bad[:2]))
