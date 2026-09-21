"""Native cubic spline IK, local curve length stretch and volume scaling."""
from adv_py.core.fit_settings import FitSkeletonValidationError


def prepare(host,plan):
    host._require_transaction();host._transaction_changed=True
    c=host._cmds
    c.createNode('transform',name='AdvPy_SplineMechanisms',parent=plan.root_path.rsplit('|',1)[0],skipSelect=True)
    c.addAttr(plan.root_path,longName='advPySplineOwner',dataType='string')
    c.setAttr(plan.root_path+'.advPySplineOwner','adv_py.spline.v2',type='string',lock=True)
    for joint in plan.joints:host.create_body_arm_mechanism_joint(joint)
    last=plan.joints[len(plan.body_joints)-1]
    host._spine_frame('AdvPy_SplineChestSpace',plan.chest_space.rsplit('|',1)[0],last.world_position,last.world_axes)


def create(host,plan):
    host._require_transaction();host._transaction_changed=True
    c=host._cmds;n=len(plan.body_joints);fk=plan.joints[:n];ik=plan.joints[n:]
    for i,(target,position) in enumerate(zip(plan.targets,plan.positions)):
        offset=target.rsplit('|',1)[0]
        host._spine_frame(f'AdvPy_SplineIK{i}Offset',plan.pelvis_control,position,plan.axes)
        control=c.circle(name=f'AdvPy_SplineIK{i}',normal=(1.,0.,0.),radius=1.5,constructionHistory=False)[0]
        c.parent(control,offset,relative=True)
        locked=['scale'+a for a in 'XYZ']+(['translate'+a for a in 'XYZ'] if i==0 else [])+(['rotate'+a for a in 'XYZ'] if i in (1,2) else [])
        for attr in locked:c.setAttr(target+'.'+attr,lock=True,keyable=False)
    for attribute,default,label in (('spineIkFk',0.,'脊柱 IK 权重'),('stretch',1.,'脊柱伸展'),('volume',1.,'体积保持')):
        c.addAttr(plan.settings,longName=attribute,niceName=label,attributeType='double',minValue=0.,maxValue=1.,defaultValue=default,keyable=True)
    curve=c.curve(name='AdvPy_SplineCurve',degree=3,point=plan.positions)
    c.parent(curve,plan.root_path,relative=True)
    shapes=c.listRelatives(plan.curve,shapes=True,fullPath=True) or []
    if len(shapes)!=1:raise FitSkeletonValidationError('Spline 曲线必须只有一个形状节点')
    c.rename(shapes[0],'AdvPy_SplineCurveShape');shape=plan.curve+'|AdvPy_SplineCurveShape'
    for i,target in enumerate(plan.targets):
        matrix=f'AdvPy_SplineIK{i}Matrix';position=f'AdvPy_SplineIK{i}Position'
        c.createNode('multMatrix',name=matrix,skipSelect=True);c.createNode('decomposeMatrix',name=position,skipSelect=True)
        c.connectAttr(target+'.worldMatrix[0]',matrix+'.matrixIn[0]')
        c.connectAttr(plan.curve+'.worldInverseMatrix[0]',matrix+'.matrixIn[1]')
        c.connectAttr(matrix+'.matrixSum',position+'.inputMatrix')
        c.connectAttr(position+'.outputTranslate',shape+f'.controlPoints[{i}]')
    c.pointConstraint(plan.pelvis_control,fk[0].path,maintainOffset=False,name='AdvPy_SplineFKRootPoint')
    c.pointConstraint(plan.targets[0],ik[0].path,maintainOffset=False,name='AdvPy_SplineIKRootPoint')
    handle,effector=c.ikHandle(name='AdvPy_SplineIKHandle',startJoint=ik[0].path,endEffector=ik[-1].path,
        solver='ikSplineSolver',curve=plan.curve,createCurve=False,parentCurve=False)
    c.rename(effector,'AdvPy_SplineIKEffector');c.parent(handle,plan.root_path)
    for attr,value in (('dTwistControlEnable',True),('dWorldUpType',4),('dForwardAxis',0),('dWorldUpAxis',0)):
        c.setAttr('AdvPy_SplineIKHandle.'+attr,value)
    for attr in ('dWorldUpVector','dWorldUpVectorEnd'):c.setAttr('AdvPy_SplineIKHandle.'+attr,0.,1.,0.,type='double3')
    c.connectAttr(plan.targets[0]+'.worldMatrix[0]','AdvPy_SplineIKHandle.dWorldUpMatrix')
    c.connectAttr(plan.targets[-1]+'.worldMatrix[0]','AdvPy_SplineIKHandle.dWorldUpMatrixEnd')
    c.orientConstraint(plan.targets[-1],ik[-1].path,maintainOffset=True,name='AdvPy_SplineChestOrient')
    c.createNode('curveInfo',name='AdvPy_SplineArc',skipSelect=True)
    c.connectAttr(shape+'.local','AdvPy_SplineArc.inputCurve')
    c.createNode('multiplyDivide',name='AdvPy_SplineRatio',skipSelect=True)
    c.setAttr('AdvPy_SplineRatio.operation',2);c.setAttr('AdvPy_SplineRatio.input2X',sum(plan.lengths))
    c.connectAttr('AdvPy_SplineArc.arcLength','AdvPy_SplineRatio.input1X')
    c.createNode('blendColors',name='AdvPy_SplineStretchBlend',skipSelect=True)
    c.connectAttr('AdvPy_SplineRatio.outputX','AdvPy_SplineStretchBlend.color1R');c.setAttr('AdvPy_SplineStretchBlend.color2R',1.)
    c.connectAttr(plan.settings+'.stretch','AdvPy_SplineStretchBlend.blender')
    c.createNode('clamp',name='AdvPy_SplineClamp',skipSelect=True)
    c.setAttr('AdvPy_SplineClamp.minR',.001);c.setAttr('AdvPy_SplineClamp.maxR',1000.)
    c.connectAttr('AdvPy_SplineStretchBlend.outputR','AdvPy_SplineClamp.inputR')
    c.createNode('multiplyDivide',name='AdvPy_SplineVolumeExponent',skipSelect=True)
    c.connectAttr(plan.settings+'.volume','AdvPy_SplineVolumeExponent.input1X');c.setAttr('AdvPy_SplineVolumeExponent.input2X',-.5)
    c.createNode('multiplyDivide',name='AdvPy_SplineVolume',skipSelect=True);c.setAttr('AdvPy_SplineVolume.operation',3)
    c.connectAttr('AdvPy_SplineClamp.outputR','AdvPy_SplineVolume.input1X');c.connectAttr('AdvPy_SplineVolumeExponent.outputX','AdvPy_SplineVolume.input2X')
    for i,joint in enumerate(ik):
        for axis in 'YZ':c.connectAttr('AdvPy_SplineVolume.outputX',joint.path+'.scale'+axis)
        if i:
            c.connectAttr(ik[i-1].path+'.scale',joint.path+'.inverseScale',force=True)
            c.createNode('multiplyDivide',name=f'AdvPy_SplineLength{i}',skipSelect=True)
            c.setAttr(f'AdvPy_SplineLength{i}.input1X',plan.lengths[i-1]);c.connectAttr('AdvPy_SplineClamp.outputR',f'AdvPy_SplineLength{i}.input2X')
            c.connectAttr(f'AdvPy_SplineLength{i}.outputX',joint.path+'.translateX')
    c.createNode('reverse',name='AdvPy_SplineReverse',skipSelect=True);c.connectAttr(plan.settings+'.spineIkFk','AdvPy_SplineReverse.inputX')
    for i in range(1,n):
        for label,command in (('Point',c.pointConstraint),('Orient',c.orientConstraint),('Scale',c.scaleConstraint)):
            node=command(fk[i].path,ik[i].path,plan.body_joints[i],name=f'AdvPy_Spline{label}{i}',maintainOffset=False)[0]
            aliases=command(node,q=True,weightAliasList=True)
            c.connectAttr('AdvPy_SplineReverse.outputX',node+'.'+aliases[0]);c.connectAttr(plan.settings+'.spineIkFk',node+'.'+aliases[1])
            if label=='Orient':c.setAttr(node+'.interpType',2)
            if label=='Scale':
                c.connectAttr(plan.body_joints[i-1]+'.scale',plan.body_joints[i]+'.inverseScale',force=True)
                plug=node+'.constraintParentInverseMatrix'
                source=c.connectionInfo(plug,sourceFromDestination=True)
                if source:c.disconnectAttr(source,plug)
                c.setAttr(plug,1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1,type='matrix',lock=True)
                c.setAttr(node+'.constraintScaleCompensate',False,lock=True)
                for target_index,source_joint in enumerate((fk[i].path,ik[i].path)):
                    world=f'AdvPy_Spline{("FK" if target_index==0 else "IK")}WorldScale{i}'
                    c.createNode('decomposeMatrix',name=world,skipSelect=True)
                    c.connectAttr(source_joint+'.worldMatrix[0]',world+'.inputMatrix')
                    c.connectAttr(world+'.outputScale',node+f'.target[{target_index}].targetScale',force=True)
                    target_parent=node+f'.target[{target_index}].targetParentMatrix'
                    source=c.connectionInfo(target_parent,sourceFromDestination=True)
                    if source:c.disconnectAttr(source,target_parent)
                    c.setAttr(target_parent,1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1,type='matrix',lock=True)
                    weight='AdvPy_SplineReverse.outputX' if target_index==0 else plan.settings+'.spineIkFk'
                    c.connectAttr(weight,node+f'.target[{target_index}].targetWeight',force=True)
    c.parentConstraint(plan.body_joints[-1],plan.chest_space,maintainOffset=False,name='AdvPy_SplineChestSpaceParent')
    c.setAttr(plan.root_path+'.visibility',False)
    audit(host,plan)


def audit(host,plan):
    c=host._cmds;n=len(plan.body_joints)
    owner=c.getAttr(plan.root_path+'.advPySplineOwner')
    if owner not in ('adv_py.spline.v1','adv_py.spline.v2'):raise FitSkeletonValidationError('Spline 所有权标记无效')
    missing=tuple(name for name in plan.node_names if not (owner=='adv_py.spline.v1' and 'WorldScale' in name) and len(c.ls(name,long=True) or [])!=1)
    if missing:raise FitSkeletonValidationError('Spline 节点缺失或名称不唯一：'+repr(missing))
    if c.ikHandle('AdvPy_SplineIKHandle',q=True,solver=True)!='ikSplineSolver':raise FitSkeletonValidationError('Spline 求解器被替换')
    shape=plan.curve+'|AdvPy_SplineCurveShape'
    edges=[(shape+'.worldSpace[0]','AdvPy_SplineIKHandle.inCurve'),(shape+'.local','AdvPy_SplineArc.inputCurve'),
        ('AdvPy_SplineArc.arcLength','AdvPy_SplineRatio.input1X'),('AdvPy_SplineRatio.outputX','AdvPy_SplineStretchBlend.color1R'),
        (plan.settings+'.stretch','AdvPy_SplineStretchBlend.blender'),('AdvPy_SplineStretchBlend.outputR','AdvPy_SplineClamp.inputR'),
        (plan.settings+'.volume','AdvPy_SplineVolumeExponent.input1X'),('AdvPy_SplineVolumeExponent.outputX','AdvPy_SplineVolume.input2X'),
        ('AdvPy_SplineClamp.outputR','AdvPy_SplineVolume.input1X'),(plan.settings+'.spineIkFk','AdvPy_SplineReverse.inputX'),
        (plan.targets[0]+'.worldMatrix[0]','AdvPy_SplineIKHandle.dWorldUpMatrix'),(plan.targets[-1]+'.worldMatrix[0]','AdvPy_SplineIKHandle.dWorldUpMatrixEnd')]
    for i,target in enumerate(plan.targets):
        edges += [(target+'.worldMatrix[0]',f'AdvPy_SplineIK{i}Matrix.matrixIn[0]'),
            (plan.curve+'.worldInverseMatrix[0]',f'AdvPy_SplineIK{i}Matrix.matrixIn[1]'),
            (f'AdvPy_SplineIK{i}Matrix.matrixSum',f'AdvPy_SplineIK{i}Position.inputMatrix'),
            (f'AdvPy_SplineIK{i}Position.outputTranslate',shape+f'.controlPoints[{i}]')]
    for i,joint in enumerate(plan.joints[n:]):
        edges += [('AdvPy_SplineVolume.outputX',joint.path+'.scale'+axis) for axis in 'YZ']
        if i:edges += [('AdvPy_SplineClamp.outputR',f'AdvPy_SplineLength{i}.input2X'),
            (f'AdvPy_SplineLength{i}.outputX',joint.path+'.translateX'),(plan.joints[n+i-1].path+'.scale',joint.path+'.inverseScale')]
    bad=[(a,b) for a,b in edges if not c.isConnected(a,b)]
    if bad:raise FitSkeletonValidationError('Spline 曲线或伸展连接被替换：'+repr(bad[:2]))
    constants={'AdvPy_SplineRatio.operation':2,'AdvPy_SplineRatio.input2X':sum(plan.lengths),
        'AdvPy_SplineStretchBlend.color2R':1.,'AdvPy_SplineClamp.minR':.001,'AdvPy_SplineClamp.maxR':1000.,
        'AdvPy_SplineVolumeExponent.operation':1,'AdvPy_SplineVolumeExponent.input2X':-.5,'AdvPy_SplineVolume.operation':3,
        'AdvPy_SplineIKHandle.dTwistControlEnable':1,'AdvPy_SplineIKHandle.dWorldUpType':4,
        'AdvPy_SplineIKHandle.dForwardAxis':0,'AdvPy_SplineIKHandle.dWorldUpAxis':0}
    constants.update({f'AdvPy_SplineLength{i}.input1X':length for i,length in enumerate(plan.lengths,1)})
    if any(abs(c.getAttr(plug)-value)>1e-8 for plug,value in constants.items()):raise FitSkeletonValidationError('Spline 求解常量被修改')
    if owner=='adv_py.spline.v2':
        identity=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
        for i in range(1,n):
            node=f'AdvPy_SplineScale{i}'
            plug=node+'.constraintParentInverseMatrix'
            if (not c.isConnected(plan.body_joints[i-1]+'.scale',plan.body_joints[i]+'.inverseScale')
                    or c.listConnections(plug,s=True,d=False) or tuple(c.getAttr(plug))!=identity
                    or c.getAttr(node+'.constraintScaleCompensate')):
                raise FitSkeletonValidationError('Spline 世界缩放补偿连接或常量被修改')
            for target_index,source_joint in enumerate((plan.joints[i].path,plan.joints[n+i].path)):
                world=f'AdvPy_Spline{("FK" if target_index==0 else "IK")}WorldScale{i}'
                target_parent=node+f'.target[{target_index}].targetParentMatrix'
                if (not c.isConnected(source_joint+'.worldMatrix[0]',world+'.inputMatrix')
                        or not c.isConnected(world+'.outputScale',node+f'.target[{target_index}].targetScale')
                        or c.listConnections(target_parent,s=True,d=False) or tuple(c.getAttr(target_parent))!=identity):
                    raise FitSkeletonValidationError('Spline 世界缩放读取网络被修改')
    for i in range(1,n):
        for label,command,kind in (('Point',c.pointConstraint,'translate'),('Orient',c.orientConstraint,'rotate'),('Scale',c.scaleConstraint,'scale')):
            node=f'AdvPy_Spline{label}{i}'
            if label!='Scale' or owner=='adv_py.spline.v1':
                sources=tuple(host._resolve_connected_node(p) for p in command(node,q=True,targetList=True))
                if sources!=(plan.joints[i].path,plan.joints[n+i].path):raise FitSkeletonValidationError('Spline FK/IK 输出目标被替换')
            aliases=("target[0].targetWeight","target[1].targetWeight") if label=="Scale" and owner=="adv_py.spline.v2" else command(node,q=True,weightAliasList=True)
            if not c.isConnected('AdvPy_SplineReverse.outputX',node+'.'+aliases[0]) or not c.isConnected(plan.settings+'.spineIkFk',node+'.'+aliases[1]):
                raise FitSkeletonValidationError('Spline 混合权重连接无效')
            for axis in 'XYZ':
                if not c.isConnected(node+'.constraint'+kind.title()+axis,plan.body_joints[i]+'.'+kind+axis):
                    raise FitSkeletonValidationError('Spline Body 输出被替换')
