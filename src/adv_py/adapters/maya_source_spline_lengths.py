"""MEL 81331–81348: stretch descendants individually, excluding IKSpEnd."""
from adv_py.core.fit_settings import FitSkeletonValidationError


def _rows(plan):
    for index,joint in enumerate(plan.native_ik[1:],1):
        yield plan.native_keys[index],joint,index==len(plan.native_ik)-1
    yield 'Tail',plan.source_solver_tail,False


def create(host,plan):
    c=host._cmds
    for key,joint,terminal in _rows(plan):
        multiply=c.createNode('multiplyDivide',name=f'AdvPy_SplineLength{key}',skipSelect=True)
        rest=float(c.getAttr(joint.path+'.translateX'))
        c.setAttr(multiply+'.input1X',rest)
        c.addAttr(multiply,longName='advPySplineRestLength',attributeType='double')
        c.setAttr(multiply+'.advPySplineRestLength',rest,lock=True)
        if terminal:
            c.setAttr(multiply+'.input2X',1.)
            c.connectAttr(multiply+'.outputX',joint.path+'.translateX')
            continue
        blend=c.createNode('blendTwoAttr',name=f'AdvPy_SplineLengthBlend{key}',skipSelect=True)
        c.setAttr(blend+'.input[0]',rest)
        c.connectAttr('AdvPy_SplineRatio.outputX',multiply+'.input2X')
        c.connectAttr(multiply+'.outputX',blend+'.input[1]')
        c.connectAttr('AdvPy_SplineStretchUnit.output',blend+'.attributesBlender')
        c.connectAttr(blend+'.output',joint.path+'.translateX')


def audit(host,plan):
    c=host._cmds;edges=[]
    for key,joint,terminal in _rows(plan):
        multiply=f'AdvPy_SplineLength{key}'
        if c.nodeType(multiply)!='multiplyDivide' or c.getAttr(multiply+'.operation')!=1:
            raise FitSkeletonValidationError('来源 Spline 长度乘法节点变化')
        recorded=c.objExists(multiply+'.advPySplineRestLength')
        rest=c.getAttr(multiply+('.advPySplineRestLength' if recorded else '.input1X'))
        if recorded and (not c.getAttr(multiply+'.advPySplineRestLength',lock=True)
                or abs(c.getAttr(multiply+'.input1X')-rest)>1e-6*max(1.,abs(rest))):
            raise FitSkeletonValidationError('来源 Spline 绑定长度变化')
        if terminal:
            if c.getAttr(multiply+'.input2X')!=1. or c.listConnections(multiply+'.input2X',s=True,d=False):
                raise FitSkeletonValidationError('来源 Spline 末端不得参与伸展')
            edges.append((multiply+'.outputX',joint.path+'.translateX'))
        else:
            blend=f'AdvPy_SplineLengthBlend{key}'
            if c.nodeType(blend)!='blendTwoAttr':
                raise FitSkeletonValidationError('来源 Spline 逐骨骼长度混合缺失')
            if abs(c.getAttr(blend+'.input[0]')-rest)>1e-6*max(1.,abs(rest)) or c.listConnections(blend+'.input[0]',s=True,d=False):
                raise FitSkeletonValidationError('来源 Spline 原始长度混合输入变化')
            edges.extend((('AdvPy_SplineRatio.outputX',multiply+'.input2X'),
                (multiply+'.outputX',blend+'.input[1]'),
                ('AdvPy_SplineStretchUnit.output',blend+'.attributesBlender'),
                (blend+'.output',joint.path+'.translateX')))
    if any(not c.isConnected(*edge) for edge in edges):
        raise FitSkeletonValidationError('来源 Spline 逐骨骼伸展连接变化')
