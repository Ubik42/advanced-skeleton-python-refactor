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
    c.parentConstraint(plan.source_follow_parent,constrained,maintainOffset=True,
                       name='AdvPy_SplineIKOffsetParent')
    main=next(path for label,path,_ in plan.source_follow_targets if label=='Main')
    c.scaleConstraint(main,constrained,maintainOffset=True,
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
        c.addAttr(plan.settings,longName='follow'+label,attributeType='double',
                  minValue=0,maxValue=10,defaultValue=default,keyable=True)
        weight=c.createNode('multDoubleLinear',name=stem+'Weight',skipSelect=True)
        c.connectAttr(plan.settings+'.follow'+label,weight+'.input1')
        c.setAttr(weight+'.input2',.1)
        c.connectAttr(weight+'.output',blend+f'.target[{index}].weight')
    output=c.createNode('multMatrix',name='AdvPy_SplineHybridFollowOutput',skipSelect=True)
    c.connectAttr(blend+'.outputMatrix',output+'.matrixIn[0]')
    c.connectAttr(parent_world_inverse(host,driven),output+'.matrixIn[1]')
    # MEL asMatrixConnectAttr gives the detached receiver its own OPM even
    # when the rest of the character uses legacy transform constraints.
    for kind,value in (('translate',0.),('rotate',0.),('scale',1.),('shear',0.)):
        c.setAttr(driven+'.'+kind,value,value,value,type='double3')
    c.connectAttr(output+'.matrixSum',driven+'.offsetParentMatrix')


def audit(host,plan):
    c=host._cmds
    parent='AdvPy_SplineIKOffsetParent'
    scale='AdvPy_SplineIKOffsetScale'
    main=next(path for label,path,_ in plan.source_follow_targets if label=='Main')
    for command,node,source in ((c.parentConstraint,parent,plan.source_follow_parent),
                                (c.scaleConstraint,scale,main)):
        targets=tuple(host._resolve_connected_node(path)
                      for path in command(node,query=True,targetList=True) or [])
        if targets!=(source,):
            raise FitSkeletonValidationError('来源 Spline 起点跟随目标改变')
    edges=[('AdvPy_SplineHybridFollowBlend.outputMatrix','AdvPy_SplineHybridFollowOutput.matrixIn[0]'),
           (parent_world_inverse(host,plan.hybrid_follow),'AdvPy_SplineHybridFollowOutput.matrixIn[1]'),
           ('AdvPy_SplineHybridFollowOutput.matrixSum',plan.hybrid_follow+'.offsetParentMatrix')]
    for index,(label,path,_) in enumerate(plan.source_follow_targets):
        stem='AdvPy_SplineHybridFollow'+label
        edges.extend(((path+'.worldMatrix[0]',stem+'Matrix.matrixIn[2]'),
                      (stem+'Matrix.matrixSum',f'AdvPy_SplineHybridFollowBlend.target[{index}].targetMatrix'),
                      (plan.settings+'.follow'+label,stem+'Weight.input1'),
                      (stem+'Weight.output',f'AdvPy_SplineHybridFollowBlend.target[{index}].weight')))
        if c.getAttr(stem+'Weight.input2')!=.1:
            raise FitSkeletonValidationError('来源 Spline Follow 权重单位改变')
    for axis in 'XYZ':
        edges.extend(((parent+'.constraintTranslate'+axis,plan.hybrid_constrained+'.translate'+axis),
                      (parent+'.constraintRotate'+axis,plan.hybrid_constrained+'.rotate'+axis),
                      (scale+'.constraintScale'+axis,plan.hybrid_constrained+'.scale'+axis)))
    if any(not c.isConnected(source,destination) for source,destination in edges):
        raise FitSkeletonValidationError('来源 Spline Follow 图连接改变')
