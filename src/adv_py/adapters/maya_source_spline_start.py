"""Original firstJointFixed and FK/IK output for each source Spline start."""
from adv_py.core.fit_settings import FitSkeletonValidationError


def create(host,plan,fk,generated_sources):
    c=host._cmds
    aliases=dict(generated_sources)
    control=next((control for control in fk.controls
        if aliases.get(control.driven_joint,control.driven_joint)==plan.body_joints[0]),None)
    if control is None:
        raise FitSkeletonValidationError('来源 Spline 起点缺少原始 FK 接收层')
    def name(value):
        return plan.node_name('AdvPy_Spline'+value)
    local=plan.driver_targets[0]+'|'+name('IKLocalOrient0')
    fixed=c.createNode('transform',name=name('IKLocalOrient3'),parent=local,skipSelect=True)
    fixed=(c.ls(fixed,long=True) or [fixed])[0]
    position=c.xform(plan.ik_outputs[0],query=True,worldSpace=True,translation=True)
    c.xform(fixed,worldSpace=True,translation=position)
    c.addAttr(plan.targets[0],longName='firstJointFixed',attributeType='double',
        minValue=0.,maxValue=10.,defaultValue=(10. if plan.body_joints[0].rsplit('|',1)[-1]=='Root_M' else 0.),
        keyable=False)
    unit=c.createNode('unitConversion',name=name('FirstFixedUnit'),skipSelect=True)
    c.setAttr(unit+'.conversionFactor',.1)
    c.connectAttr(plan.targets[0]+'.firstJointFixed',unit+'.input')
    blend=c.createNode('blendMatrix',name=name('FirstFixedBM'),skipSelect=True)
    c.connectAttr(plan.ik_outputs[0]+'.worldMatrix[0]',blend+'.inputMatrix')
    c.connectAttr(fixed+'.worldMatrix[0]',blend+'.target[0].targetMatrix')
    c.connectAttr(unit+'.output',blend+'.target[0].weight')
    output=c.createNode('transform',name=name('FirstFixedOutput'),parent=plan.root_path,skipSelect=True)
    output=(c.ls(output,long=True) or [output])[0]
    matrix=c.createNode('multMatrix',name=name('FirstFixedMM'),skipSelect=True)
    c.connectAttr(blend+'.outputMatrix',matrix+'.matrixIn[0]')
    c.connectAttr(output+'.parentInverseMatrix[0]',matrix+'.matrixIn[1]')
    c.connectAttr(matrix+'.matrixSum',output+'.offsetParentMatrix')
    source=control.source_override_path or control.sub_control_path or control.control_path
    if control.driven_joint!=plan.body_joints[0]:
        # A nested Spline starts on an output already owned by the upstream
        # Spline. Its upstream FK mechanism must stay a pure FK receiver.
        return fixed,output
    # These constraints retain the existing FK node identities so source
    # rebuild and animation-channel reconciliation see the same receivers.
    for command,node in ((c.orientConstraint,control.constraint_name),
                         (c.pointConstraint,control.translation_constraint_name)):
        if node is None:
            continue
        if not c.objExists(node):
            raise FitSkeletonValidationError('来源 Spline 起点约束缺失：'+node)
        target_list=command(node,query=True,targetList=True) or ()
        if len(target_list)!=1:
            raise FitSkeletonValidationError('来源 Spline 起点 FK 约束目标不唯一：'+node)
        c.delete(node)
        constraint=command(source,output,control.driven_joint,
                           maintainOffset=False,name=node)[0]
        weights=command(constraint,query=True,weightAliasList=True)
        if len(weights)!=2:
            raise FitSkeletonValidationError('来源 Spline 起点 FK／IK 输出目标不完整')
        c.connectAttr(plan.node_name('AdvPy_SplineReverse.outputX'),constraint+'.'+weights[0])
        c.connectAttr(plan.settings+'.spineIkFk',constraint+'.'+weights[1])
        if command==c.orientConstraint:
            c.setAttr(constraint+'.interpType',2)
    return fixed,output
