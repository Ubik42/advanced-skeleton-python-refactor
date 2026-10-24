"""ADV asFollowLevels graph for the detached first IKhybrid Extra receiver."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_source_parent_inverse import parent_world_inverse


def _matrix(value):
    if len(value)==1 and isinstance(value[0],(tuple,list)):
        value=value[0]
    return tuple(value)


def create(host,plan):
    c=host._cmds
    constrained=plan.hybrid_constrained
    main=next(path for label,path,_ in plan.source_follow_targets if label=='Main')
    if plan.source_native_follow and plan.use_offset_parent_matrix:
        parent=c.createNode('multMatrix',name='AdvPy_SplineIKOffsetParentMM',skipSelect=True)
        c.connectAttr(plan.source_follow_parent+'.worldMatrix[0]',parent+'.matrixIn[0]')
        c.connectAttr(parent_world_inverse(host,constrained),parent+'.matrixIn[1]')
        for kind,value in (('translate',0.),('rotate',0.),('scale',1.),('shear',0.)):
            c.setAttr(constrained+'.'+kind,value,value,value,type='double3')
        c.connectAttr(parent+'.matrixSum',constrained+'.offsetParentMatrix')
    else:
        c.parentConstraint(plan.source_follow_parent,constrained,maintainOffset=not plan.source_native_follow,
                           name='AdvPy_SplineIKOffsetParent')
        c.scaleConstraint(main,constrained,maintainOffset=not plan.source_native_follow,
                          name='AdvPy_SplineIKOffsetScale')
    driven=plan.hybrid_follow
    bind=_matrix(c.xform(driven,query=True,worldSpace=True,matrix=True))
    blend=c.createNode('blendMatrix',name='AdvPy_SplineHybridFollowBlend',skipSelect=True)
    c.setAttr(blend+'.inputMatrix',*bind,type='matrix')
    for index,(label,path,default) in enumerate(plan.source_follow_targets):
        stem='AdvPy_SplineHybridFollow'+label
        matrix=c.createNode('multMatrix',name=stem+'Matrix',skipSelect=True)
        inverse=_matrix(c.getAttr(path+'.worldInverseMatrix[0]'))
        c.setAttr(matrix+'.matrixIn[0]',*bind,type='matrix')
        c.setAttr(matrix+'.matrixIn[1]',*inverse,type='matrix')
        c.connectAttr(path+'.worldMatrix[0]',matrix+'.matrixIn[2]')
        c.connectAttr(matrix+'.matrixSum',blend+f'.target[{index}].targetMatrix')
        # MEL 74470-74481 defines the attribute first; 81479-81480 then
        # sets followRoot's current value to 10. On nested Spline chains its
        # declared default stays 0, so reset-to-default must keep that value.
        declared_default = (10. if label == 'Main' or index == len(plan.source_follow_targets)-1
                            else 0.) if plan.source_native_follow else default
        c.addAttr(plan.settings,longName='follow'+label,attributeType='double',
                  minValue=0,maxValue=10,defaultValue=declared_default,keyable=True)
        if declared_default != default:
            c.setAttr(plan.settings+'.follow'+label,default)
        weight=c.createNode('multDoubleLinear',name=stem+'Weight',skipSelect=True)
        c.connectAttr(plan.settings+'.follow'+label,weight+'.input1')
        c.setAttr(weight+'.input2',.1)
        c.connectAttr(weight+'.output',blend+f'.target[{index}].weight')
    output=c.createNode('multMatrix',name='AdvPy_SplineHybridFollowOutput',skipSelect=True)
    c.connectAttr(blend+'.outputMatrix',output+'.matrixIn[0]')
    c.connectAttr(parent_world_inverse(host,driven),output+'.matrixIn[1]')
    for kind,value in (('translate',0.),('rotate',0.),('scale',1.),('shear',0.)):
        c.setAttr(driven+'.'+kind,value,value,value,type='double3')
    if not plan.source_native_follow or plan.use_offset_parent_matrix:
        c.connectAttr(output+'.matrixSum',driven+'.offsetParentMatrix')
    else:
        # MEL asMatrixConnectAttr preserves all native TRS/shear outputs.
        dm=c.createNode('decomposeMatrix',name='AdvPy_SplineHybridFollowDM',skipSelect=True)
        c.setAttr(dm+'.inputRotateOrder',c.getAttr(driven+'.rotateOrder'))
        c.connectAttr(output+'.matrixSum',dm+'.inputMatrix')
        for kind in ('Translate','Rotate','Scale'):
            for axis in 'XYZ':c.connectAttr(dm+'.output'+kind+axis,driven+'.'+kind.lower()+axis)
        for axis,component in zip('XYZ',('XY','XZ','YZ')):
            c.connectAttr(dm+'.outputShear'+axis,driven+'.shear'+component)


def audit(host,plan):
    c=host._cmds
    if plan.source_native_follow and (c.getAttr(plan.source_controls_root+'.inheritsTransform') or
            not c.getAttr(plan.source_controls_root+'.inheritsTransform',lock=True)):
        raise FitSkeletonValidationError('来源 Spline 控制根重复继承 Main 变换')
    parent='AdvPy_SplineIKOffsetParent'
    scale='AdvPy_SplineIKOffsetScale'
    main=next(path for label,path,_ in plan.source_follow_targets if label=='Main')
    if not (plan.source_native_follow and plan.use_offset_parent_matrix):
        for command,node,source in ((c.parentConstraint,parent,plan.source_follow_parent),
                                    (c.scaleConstraint,scale,main)):
            targets=tuple(host._resolve_connected_node(path)
                          for path in command(node,query=True,targetList=True) or [])
            if targets!=(source,):
                raise FitSkeletonValidationError('来源 Spline 起点跟随目标改变')
        if plan.source_native_follow:
            for attr in ('target[0].targetOffsetTranslate','target[0].targetOffsetRotate'):
                if any(abs(v)>1e-8 for v in c.getAttr(parent+'.'+attr)[0]):
                    raise FitSkeletonValidationError('来源 Spline 起点错误保留了父约束偏移')
            if any(abs(v-1.)>1e-8 for v in c.getAttr(scale+'.offset')[0]):
                raise FitSkeletonValidationError('来源 Spline Main 缩放约束偏移改变')
    edges=[('AdvPy_SplineHybridFollowBlend.outputMatrix','AdvPy_SplineHybridFollowOutput.matrixIn[0]'),
           (parent_world_inverse(host,plan.hybrid_follow),'AdvPy_SplineHybridFollowOutput.matrixIn[1]')]
    if plan.source_native_follow and plan.use_offset_parent_matrix:
        matrix='AdvPy_SplineIKOffsetParentMM'
        edges.extend(((plan.source_follow_parent+'.worldMatrix[0]',matrix+'.matrixIn[0]'),
            (parent_world_inverse(host,plan.hybrid_constrained),matrix+'.matrixIn[1]'),
            (matrix+'.matrixSum',plan.hybrid_constrained+'.offsetParentMatrix'),
            ('AdvPy_SplineHybridFollowOutput.matrixSum',plan.hybrid_follow+'.offsetParentMatrix')))
        for attr,value in (('translate',0.),('rotate',0.),('scale',1.),('shear',0.)):
            if c.listConnections(plan.hybrid_constrained+'.'+attr,s=True,d=False) or any(
                    abs(v-value)>1e-8 for v in c.getAttr(plan.hybrid_constrained+'.'+attr)[0]):
                raise FitSkeletonValidationError('来源 Spline OPM 跟随本地变换改变')
    elif plan.source_native_follow:
        dm='AdvPy_SplineHybridFollowDM'
        edges.append(('AdvPy_SplineHybridFollowOutput.matrixSum',dm+'.inputMatrix'))
        if c.getAttr(dm+'.inputRotateOrder')!=c.getAttr(plan.hybrid_follow+'.rotateOrder'):
            raise FitSkeletonValidationError('来源 Spline Follow 旋转顺序变化')
        for kind in ('Translate','Rotate','Scale'):
            for axis in 'XYZ':edges.append((dm+'.output'+kind+axis,plan.hybrid_follow+'.'+kind.lower()+axis))
        for axis,component in zip('XYZ',('XY','XZ','YZ')):
            edges.append((dm+'.outputShear'+axis,plan.hybrid_follow+'.shear'+component))
    else:edges.append(('AdvPy_SplineHybridFollowOutput.matrixSum',plan.hybrid_follow+'.offsetParentMatrix'))
    for index,(label,path,_) in enumerate(plan.source_follow_targets):
        stem='AdvPy_SplineHybridFollow'+label
        edges.extend(((path+'.worldMatrix[0]',stem+'Matrix.matrixIn[2]'),
                      (stem+'Matrix.matrixSum',f'AdvPy_SplineHybridFollowBlend.target[{index}].targetMatrix'),
                      (plan.settings+'.follow'+label,stem+'Weight.input1'),
                      (stem+'Weight.output',f'AdvPy_SplineHybridFollowBlend.target[{index}].weight')))
        if c.getAttr(stem+'Weight.input2')!=.1:
            raise FitSkeletonValidationError('来源 Spline Follow 权重单位改变')
    if not (plan.source_native_follow and plan.use_offset_parent_matrix):
        for axis in 'XYZ':
            edges.extend(((parent+'.constraintTranslate'+axis,plan.hybrid_constrained+'.translate'+axis),
                          (parent+'.constraintRotate'+axis,plan.hybrid_constrained+'.rotate'+axis),
                          (scale+'.constraintScale'+axis,plan.hybrid_constrained+'.scale'+axis)))
    if any(not c.isConnected(source,destination) for source,destination in edges):
        raise FitSkeletonValidationError('来源 Spline Follow 图连接改变')
