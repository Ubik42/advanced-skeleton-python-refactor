"""Project middle Spline IK controller twist into Maya's twist ramp."""
from __future__ import annotations

import json

from adv_py.core.fit_settings import FitSkeletonValidationError


def create(host, plan):
    c = host._cmds
    count = len(plan.targets)
    if count < 3 or len(plan.body_joints) <= 2:
        raise FitSkeletonValidationError('Spline 中间扭转需要多段 IK 链')
    ramp = c.createNode('ramp', name='AdvPy_SplineTwistRamp', skipSelect=True)
    c.setAttr(ramp+'.interpolation', 1)
    c.setAttr('AdvPy_SplineIKHandle.dTwistValueType', 2)
    c.setAttr('AdvPy_SplineIKHandle.dTwistRampMult', 3.333)
    c.connectAttr(ramp+'.outColor', 'AdvPy_SplineIKHandle.dTwistRamp')
    for index in range(count):
        entry = f'{ramp}.colorEntryList[{index}]'
        c.setAttr(entry+'.color', 0., 0., 0., type='double3')
        c.setAttr(entry+'.position', index/(count-1))
        if index in (0, count-1):
            continue
        control = plan.driver_targets[index]
        offset = plan.offset_targets[index]
        relative = c.createNode('multMatrix',
            name=f'AdvPy_SplineTwistRelative{index}', skipSelect=True)
        decompose = c.createNode('decomposeMatrix',
            name=f'AdvPy_SplineTwistDecompose{index}', skipSelect=True)
        quat = c.createNode('quatToEuler',
            name=f'AdvPy_SplineTwistQuatToEuler{index}', skipSelect=True)
        if plan.source_solver_tail is not None:
            from maya.api import OpenMaya as om
            # LocalOrient0 follows the curve tangent; LocalOrient2 is the
            # separate start-joint frame used by scaling and solver up axes.
            local=host._spine_frame(f'AdvPy_SplineTwistLocalOrient{index}',control,
                plan.positions[index],plan.source_control_axes[index] if plan.source_control_axes else plan.axes)
            c.addAttr(local,longName='advPySplineTwistLocalBind',dataType='string')
            c.setAttr(local+'.advPySplineTwistLocalBind',json.dumps(tuple(c.getAttr(local+'.matrix'))),type='string',lock=True)
            for kind,axes in (('translate','XYZ'),('rotate','XYZ'),('scale','XYZ'),('shear',('XY','XZ','YZ'))):
                for axis in axes:c.setAttr(local+'.'+kind+axis,lock=True,keyable=False)
            inverse=tuple(om.MMatrix(c.getAttr(local+'.worldMatrix[0]')).inverse())
            reference=c.createNode('multMatrix',name=f'AdvPy_SplineTwistOffsetRelative{index}',skipSelect=True)
            c.connectAttr(offset+'.worldInverseMatrix[0]',reference+'.matrixIn[0]')
            c.addAttr(reference,longName='advPySplineSourceBind',dataType='matrix')
            c.setAttr(reference+'.advPySplineSourceBind',*inverse,type='matrix',lock=True)
            c.addAttr(reference,longName='advPySplineSourceBindRecord',dataType='string')
            c.setAttr(reference+'.advPySplineSourceBindRecord',json.dumps(inverse),type='string',lock=True)
            c.connectAttr(reference+'.advPySplineSourceBind',reference+'.matrixIn[1]')
            c.connectAttr(local+'.worldMatrix[0]',relative+'.matrixIn[0]')
            c.connectAttr(reference+'.matrixSum',relative+'.matrixIn[1]')
        else:
            c.connectAttr(control+'.worldMatrix[0]', relative+'.matrixIn[0]')
            c.connectAttr(offset+'.worldInverseMatrix[0]', relative+'.matrixIn[1]')
        c.connectAttr(relative+'.matrixSum', decompose+'.inputMatrix')
        for component in 'XW':
            c.connectAttr(decompose+'.outputQuat'+component,
                          quat+'.inputQuat'+component)
        c.connectAttr(quat+'.outputRotateX', entry+'.colorR')


def audit(host, plan):
    c = host._cmds
    count = len(plan.targets)
    ramp = 'AdvPy_SplineTwistRamp'
    if (c.nodeType(ramp) != 'ramp'
            or c.getAttr(ramp+'.interpolation') != 1
            or c.getAttr('AdvPy_SplineIKHandle.dTwistValueType') != 2
            or abs(c.getAttr('AdvPy_SplineIKHandle.dTwistRampMult')-3.333)>1e-6
            or not c.isConnected(ramp+'.outColor',
                                 'AdvPy_SplineIKHandle.dTwistRamp')):
        raise FitSkeletonValidationError('Spline 中间扭转曲线配置无效')
    edges = []
    for index in range(count):
        entry = f'{ramp}.colorEntryList[{index}]'
        if abs(c.getAttr(entry+'.position')-index/(count-1))>1e-6:
            raise FitSkeletonValidationError('Spline 中间扭转曲线位置被修改')
        if index in (0, count-1):
            if any(abs(value)>1e-8 for value in c.getAttr(entry+'.color')[0]):
                raise FitSkeletonValidationError('Spline 扭转曲线端点不为零')
            continue
        control = plan.driver_targets[index]
        offset = plan.offset_targets[index]
        for axis in 'XYZ':
            if (c.getAttr(control+'.rotate'+axis, lock=True)
                    or not c.getAttr(control+'.rotate'+axis, keyable=True)):
                raise FitSkeletonValidationError('Spline 中间旋转通道不可动画')
        relative = f'AdvPy_SplineTwistRelative{index}'
        decompose = f'AdvPy_SplineTwistDecompose{index}'
        quat = f'AdvPy_SplineTwistQuatToEuler{index}'
        if plan.source_solver_tail is not None:
            reference=f'AdvPy_SplineTwistOffsetRelative{index}'
            local=control+f'|AdvPy_SplineTwistLocalOrient{index}'
            if (not c.getAttr(local+'.advPySplineTwistLocalBind',lock=True)
                    or tuple(json.loads(c.getAttr(local+'.advPySplineTwistLocalBind')))!=tuple(c.getAttr(local+'.matrix'))):
                raise FitSkeletonValidationError('来源 Spline 扭转切线局部坐标变化')
            edges.extend(((offset+'.worldInverseMatrix[0]',reference+'.matrixIn[0]'),
                (reference+'.advPySplineSourceBind',reference+'.matrixIn[1]')))
            if (not c.getAttr(reference+'.advPySplineSourceBind',lock=True)
                    or not c.getAttr(reference+'.advPySplineSourceBindRecord',lock=True)
                    or tuple(json.loads(c.getAttr(reference+'.advPySplineSourceBindRecord')))!=tuple(c.getAttr(reference+'.advPySplineSourceBind'))):
                raise FitSkeletonValidationError('来源 Spline 扭转投影绑定矩阵变化')
            first=local+'.worldMatrix[0]';second=reference+'.matrixSum'
        else:first=control+'.worldMatrix[0]';second=offset+'.worldInverseMatrix[0]'
        edges.extend(((first,relative+'.matrixIn[0]'),
                      (second,relative+'.matrixIn[1]'),
                      (relative+'.matrixSum',decompose+'.inputMatrix'),
                      (decompose+'.outputQuatX',quat+'.inputQuatX'),
                      (decompose+'.outputQuatW',quat+'.inputQuatW'),
                      (quat+'.outputRotateX',entry+'.colorR')))
    # Angle output -> ramp float inserts Maya's native unitConversion.
    # Other edges must remain direct.
    bad = [(source, destination) for source, destination in edges
           if not c.isConnected(source, destination,
                ignoreUnitConversion=source.endswith('.outputRotateX'))]
    if bad:
        raise FitSkeletonValidationError('Spline 中间扭转图连接被替换：'+repr(bad[:2]))
