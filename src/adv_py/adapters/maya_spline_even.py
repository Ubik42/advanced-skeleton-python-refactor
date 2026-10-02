"""Curve-sampled and native Spline IK outputs for ADV stretchEven."""
from __future__ import annotations

from adv_py.core.fit_settings import FitSkeletonValidationError


def create(host, plan, shape, ik):
    c = host._cmds
    n = len(ik)
    c.addAttr(plan.settings, longName='stretchEven', niceName='均匀伸展',
              attributeType='double', minValue=0., maxValue=10.,
              defaultValue=0., keyable=True)
    c.createNode('unitConversion', name='AdvPy_SplineStretchEvenUnit', skipSelect=True)
    c.setAttr('AdvPy_SplineStretchEvenUnit.conversionFactor', .1)
    c.connectAttr(plan.settings+'.stretchEven', 'AdvPy_SplineStretchEvenUnit.input')
    c.createNode('reverse', name='AdvPy_SplineStretchEvenReverse', skipSelect=True)
    c.connectAttr('AdvPy_SplineStretchEvenUnit.output',
                  'AdvPy_SplineStretchEvenReverse.inputX')
    c.createNode('multiplyDivide', name='AdvPy_SplineStretchEvenWeight', skipSelect=True)
    c.connectAttr('AdvPy_SplineStretchUnit.output',
                  'AdvPy_SplineStretchEvenWeight.input1X')
    c.connectAttr('AdvPy_SplineStretchEvenReverse.outputX',
                  'AdvPy_SplineStretchEvenWeight.input2X')

    if plan.source_ik_chain:
        from . import maya_source_spline_outputs
        maya_source_spline_outputs.create(host,plan,shape,ik)
        return

    nearest = c.createNode('nearestPointOnCurve', skipSelect=True)
    c.connectAttr(shape+'.worldSpace[0]', nearest+'.inputCurve')
    arcs = []
    outputs = []
    for ordinal, joint in enumerate(ik):
        i=plan.native_keys[ordinal]
        bind = tuple(c.xform(joint.path, query=True, worldSpace=True, matrix=True))
        for axis, value in zip('XYZ', bind[12:15]):
            c.setAttr(nearest+'.inPosition'+axis, value)
        parameter = c.getAttr(nearest+'.parameter')
        sample = c.createNode('pointOnCurveInfo',
                              name=f'AdvPy_SplineIKArcSample{i}', skipSelect=True)
        c.connectAttr(shape+'.worldSpace[0]', sample+'.inputCurve')
        c.setAttr(sample+'.turnOnPercentage', False)
        c.setAttr(sample+'.parameter', parameter, lock=True)
        arc = c.createNode('transform', name=f'AdvPy_SplineIKArcFrame{i}',
                           parent=plan.root_path, skipSelect=True)
        arc = (c.ls(arc, long=True) or [arc])[0]
        c.setAttr(arc+'.inheritsTransform', False, lock=True)
        c.xform(arc, worldSpace=True, matrix=bind)
        c.connectAttr(sample+'.position', arc+'.translate')
        arcs.append(arc)
        output = c.createNode('transform', name=f'AdvPy_SplineIKOutput{i}',
                              parent=plan.root_path, skipSelect=True)
        output = (c.ls(output, long=True) or [output])[0]
        c.setAttr(output+'.inheritsTransform', False, lock=True)
        c.xform(output, worldSpace=True, matrix=bind)
        outputs.append(output)
    c.delete(nearest)

    for ordinal, arc in enumerate(arcs):
        i=plan.native_keys[ordinal]
        if ordinal == n-1:
            c.orientConstraint(plan.driver_targets[-1], arc, maintainOffset=True,
                               name=f'AdvPy_SplineIKArcEndOrient{i}')
        else:
            c.aimConstraint(arcs[ordinal+1], arc, maintainOffset=True,
                            aimVector=(1, 0, 0), upVector=(0, 1, 0),
                            worldUpType='objectrotation',
                            worldUpObject=ik[ordinal].path,
                            name=f'AdvPy_SplineIKArcAim{i}')
    for ordinal, (joint, arc, output) in enumerate(zip(ik, arcs, outputs)):
        i=plan.native_keys[ordinal]
        weight = ('AdvPy_SplineStretchUnit.output' if ordinal == n-1 else
                  'AdvPy_SplineStretchEvenWeight.outputX')
        reverse = c.createNode('reverse',
                               name=f'AdvPy_SplineIKOutputReverse{i}',
                               skipSelect=True)
        c.connectAttr(weight, reverse+'.inputX')
        for label, command in (('Point', c.pointConstraint),
                               ('Orient', c.orientConstraint)):
            node = command(joint.path, arc, output, maintainOffset=False,
                           name=f'AdvPy_SplineIKOutput{label}{i}')[0]
            aliases = command(node, query=True, weightAliasList=True)
            if len(aliases) != 2:
                raise FitSkeletonValidationError('Spline 双链输出约束目标不完整')
            c.connectAttr(reverse+'.outputX', node+'.'+aliases[0])
            c.connectAttr(weight, node+'.'+aliases[1])
            if label == 'Orient':
                c.setAttr(node+'.interpType', 2)
        c.scaleConstraint(joint.path, output, maintainOffset=False,
                          name=f'AdvPy_SplineIKOutputScale{i}')


def audit(host, plan, shape, ik):
    c = host._cmds
    n = len(ik)
    if (not c.attributeQuery('stretchEven', node=plan.settings, exists=True)
            or c.getAttr(plan.settings+'.stretchEven', type=True) != 'double'):
        raise FitSkeletonValidationError('Spline stretchEven 控制属性缺失')
    edges = [(plan.settings+'.stretchEven',
              'AdvPy_SplineStretchEvenUnit.input'),
             ('AdvPy_SplineStretchEvenUnit.output',
              'AdvPy_SplineStretchEvenReverse.inputX'),
             ('AdvPy_SplineStretchUnit.output',
              'AdvPy_SplineStretchEvenWeight.input1X'),
             ('AdvPy_SplineStretchEvenReverse.outputX',
              'AdvPy_SplineStretchEvenWeight.input2X')]
    if abs(c.getAttr('AdvPy_SplineStretchEvenUnit.conversionFactor')-.1)>1e-9:
        raise FitSkeletonValidationError('Spline stretchEven 量纲被修改')
    if plan.source_ik_chain:
        if any(not c.isConnected(*edge) for edge in edges):
            raise FitSkeletonValidationError('来源 Spline stretchEven 权重接线被修改')
        from . import maya_source_spline_outputs
        maya_source_spline_outputs.audit(host,plan,shape,ik)
        return
    for ordinal, joint in enumerate(ik):
        i=plan.native_keys[ordinal]
        sample = f'AdvPy_SplineIKArcSample{i}'
        arc = plan.root_path+f'|AdvPy_SplineIKArcFrame{i}'
        output = plan.root_path+f'|AdvPy_SplineIKOutput{i}'
        if (c.nodeType(sample) != 'pointOnCurveInfo'
                or not c.getAttr(sample+'.parameter', lock=True)
                or c.getAttr(sample+'.turnOnPercentage')
                or c.getAttr(arc+'.inheritsTransform')
                or c.getAttr(output+'.inheritsTransform')):
            raise FitSkeletonValidationError('Spline 曲线采样或双链输出层无效')
        edges.extend(((shape+'.worldSpace[0]', sample+'.inputCurve'),
                      (sample+'.position', arc+'.translate')))
        if ordinal == n-1:
            command = c.orientConstraint
            node = f'AdvPy_SplineIKArcEndOrient{i}'
            targets = (plan.driver_targets[-1],)
        else:
            command = c.aimConstraint
            node = f'AdvPy_SplineIKArcAim{i}'
            targets = (plan.root_path+f'|AdvPy_SplineIKArcFrame{plan.native_keys[ordinal+1]}',)
        actual = tuple(host._resolve_connected_node(p)
                       for p in command(node, query=True, targetList=True))
        if actual != targets:
            raise FitSkeletonValidationError('Spline 曲线采样朝向目标被替换')
        edges.extend((node+'.constraintRotate'+axis, arc+'.rotate'+axis)
                     for axis in 'XYZ')
        for label, command in (('Point', c.pointConstraint),
                               ('Orient', c.orientConstraint)):
            node = f'AdvPy_SplineIKOutput{label}{i}'
            actual = tuple(host._resolve_connected_node(p)
                           for p in command(node, query=True, targetList=True))
            aliases = command(node, query=True, weightAliasList=True)
            if actual != (joint.path, arc) or len(aliases) != 2:
                raise FitSkeletonValidationError('Spline 双链输出目标被替换')
            weight = ('AdvPy_SplineStretchUnit.output' if ordinal == n-1 else
                      'AdvPy_SplineStretchEvenWeight.outputX')
            edges.extend(((weight, f'AdvPy_SplineIKOutputReverse{i}.inputX'),
                          (f'AdvPy_SplineIKOutputReverse{i}.outputX',
                           node+'.'+aliases[0]),
                          (weight, node+'.'+aliases[1])))
            if label == 'Orient' and c.getAttr(node+'.interpType') != 2:
                raise FitSkeletonValidationError('Spline 双链朝向插值已改变')
            for axis in 'XYZ':
                attribute = ('Translate' if label == 'Point' else 'Rotate')+axis
                edges.append((node+'.constraint'+attribute,
                              output+'.'+('translate' if label == 'Point'
                                          else 'rotate')+axis))
        scale = f'AdvPy_SplineIKOutputScale{i}'
        targets = tuple(host._resolve_connected_node(p)
                        for p in c.scaleConstraint(scale, query=True,
                                                   targetList=True))
        if targets != (joint.path,):
            raise FitSkeletonValidationError('Spline 双链缩放目标被替换')
        edges.extend((scale+'.constraintScale'+axis,
                      output+'.scale'+axis) for axis in 'XYZ')
    bad = [(source, target) for source, target in edges
           if not c.isConnected(source, target)]
    if bad:
        raise FitSkeletonValidationError('Spline stretchEven 图连接被替换：'+repr(bad[:2]))
