"""MEL 81525–81695: correct IKSp/IKAc independently, then blend world matrices."""
import json
from adv_py.core.fit_settings import FitSkeletonValidationError


def _names(key):
    return {kind:f'AdvPy_SplineIK{kind}{key}' for kind in
            ('ArcSample','ArcPoint','ArcFrame','ArcAimMatrix','ArcLocalMM','ArcLocalPM','ArcWorldMM','SpFollowMM',
             'AcFollowMM','AcFollowPM','AcFollowWorldMM','Output','OutputBM')}


def create(host,plan,shape,ik):
    from maya.api import OpenMaya as om
    c=host._cmds;keys=plan.native_keys
    binds=[tuple(c.xform(j.source_joint,q=True,ws=True,matrix=True)) for j in ik]
    nearest=c.createNode('nearestPointOnCurve',skipSelect=True)
    c.connectAttr(shape+'.worldSpace[0]',nearest+'.inputCurve')
    for key,joint in zip(keys,ik):
        names=_names(key)
        position=c.xform(joint.path,q=True,ws=True,translation=True)
        c.setAttr(nearest+'.inPosition',*position)
        parameter=c.getAttr(nearest+'.parameter')
        sample=c.createNode('pointOnCurveInfo',name=names['ArcSample'],skipSelect=True)
        c.connectAttr(shape+'.worldSpace[0]',sample+'.inputCurve')
        c.setAttr(sample+'.parameter',parameter,lock=True)
        point=c.createNode('transform',name=names['ArcPoint'],parent=plan.root_path,skipSelect=True)
        c.setAttr(point+'.inheritsTransform',False,lock=True)
        c.connectAttr(sample+'.position',point+'.translate')
        arc=c.createNode('transform',name=names['ArcFrame'],parent=plan.root_path,skipSelect=True)
        c.setAttr(arc+'.inheritsTransform',False,lock=True)
    c.delete(nearest)
    # Last Ac frame follows the endpoint's authored LocalOrient2 axes.
    last=_names(keys[-1]);end=plan.driver_targets[-1]+f'|AdvPy_SplineIKLocalOrient{len(plan.targets)-1}'
    orient=c.createNode('pickMatrix',name='AdvPy_SplineIKArcEndRotation',skipSelect=True)
    pos=c.createNode('pickMatrix',name='AdvPy_SplineIKArcEndPosition',skipSelect=True)
    mix=c.createNode('multMatrix',name='AdvPy_SplineIKArcEndMatrix',skipSelect=True)
    c.connectAttr(end+'.worldMatrix[0]',orient+'.inputMatrix')
    for attr in ('useTranslate','useScale','useShear'):c.setAttr(orient+'.'+attr,False)
    c.connectAttr(last['ArcPoint']+'.worldMatrix[0]',pos+'.inputMatrix')
    for attr in ('useRotate','useScale','useShear'):c.setAttr(pos+'.'+attr,False)
    c.connectAttr(orient+'.outputMatrix',mix+'.matrixIn[0]');c.connectAttr(pos+'.outputMatrix',mix+'.matrixIn[1]')
    _arc_world(c,plan,last,mix+'.matrixSum')
    for index,(key,joint) in enumerate(zip(keys[:-1],ik[:-1])):
        names=_names(key);aim=c.createNode('aimMatrix',name=names['ArcAimMatrix'],skipSelect=True)
        c.setAttr(aim+'.secondaryMode',2)
        c.setAttr(aim+'.secondaryInputAxis',0.,1.,0.)
        c.setAttr(aim+'.secondaryTargetVector',0.,1.,0.)
        c.connectAttr(names['ArcPoint']+'.worldMatrix[0]',aim+'.inputMatrix')
        c.connectAttr(_names(keys[index+1])['ArcFrame']+'.worldMatrix[0]',aim+'.primaryTargetMatrix')
        c.connectAttr(joint.path+'.worldMatrix[0]',aim+'.secondaryTargetMatrix')
        _arc_world(c,plan,names,aim+'.outputMatrix')
    for index,(key,joint,bind) in enumerate(zip(keys,ik,binds)):
        names=_names(key)
        for kind,source in (('SpFollowMM',joint.path),('AcFollowMM',names['ArcFrame'])):
            matrix=c.createNode('multMatrix',name=names[kind],skipSelect=True)
            offset=tuple(om.MMatrix(bind)*om.MMatrix(c.getAttr(source+'.worldMatrix[0]')).inverse())
            c.addAttr(matrix,longName='advPySplineSourceBind',dataType='matrix')
            c.setAttr(matrix+'.advPySplineSourceBind',*offset,type='matrix',lock=True)
            c.addAttr(matrix,longName='advPySplineSourceBindRecord',dataType='string')
            c.setAttr(matrix+'.advPySplineSourceBindRecord',json.dumps(offset),type='string',lock=True)
            c.connectAttr(matrix+'.advPySplineSourceBind',matrix+'.matrixIn[0]')
            c.connectAttr(source+'.worldMatrix[0]',matrix+'.matrixIn[1]')
        pick=c.createNode('pickMatrix',name=names['AcFollowPM'],skipSelect=True)
        c.connectAttr(plan.scale_reference+'.worldInverseMatrix[0]',names['AcFollowMM']+'.matrixIn[2]')
        c.connectAttr(names['AcFollowMM']+'.matrixSum',pick+'.inputMatrix')
        c.setAttr(pick+'.useScale',False);c.setAttr(pick+'.useShear',False)
        blend=c.createNode('blendMatrix',name=names['OutputBM'],skipSelect=True)
        c.connectAttr(names['SpFollowMM']+'.matrixSum',blend+'.inputMatrix')
        world=c.createNode('multMatrix',name=names['AcFollowWorldMM'],skipSelect=True)
        c.connectAttr(pick+'.outputMatrix',world+'.matrixIn[0]')
        c.connectAttr(plan.scale_reference+'.worldMatrix[0]',world+'.matrixIn[1]')
        c.connectAttr(world+'.matrixSum',blend+'.target[0].targetMatrix')
        c.connectAttr('AdvPy_SplineStretchUnit.output' if index==len(keys)-1 else
                      'AdvPy_SplineStretchEvenWeight.outputX',blend+'.target[0].weight')
        output=c.createNode('transform',name=names['Output'],parent=plan.root_path,skipSelect=True)
        c.setAttr(output+'.inheritsTransform',False,lock=True)
        c.connectAttr(blend+'.outputMatrix',output+'.offsetParentMatrix')


def audit(host,plan,shape,ik):
    c=host._cmds;keys=plan.native_keys;edges=[]
    for index,(key,joint) in enumerate(zip(keys,ik)):
        names=_names(key)
        sample=names['ArcSample'];point=names['ArcPoint'];arc=names['ArcFrame'];output=names['Output']
        if (c.nodeType(sample)!='pointOnCurveInfo' or not c.getAttr(sample+'.parameter',lock=True)
                or c.getAttr(sample+'.turnOnPercentage')):
            raise FitSkeletonValidationError('来源 Spline 曲线采样被修改')
        for transform in (point,arc,output):
            if c.getAttr(transform+'.inheritsTransform') or not c.getAttr(transform+'.inheritsTransform',lock=True):
                raise FitSkeletonValidationError('来源 Spline 世界矩阵层继承被修改')
        edges.extend(((shape+'.worldSpace[0]',sample+'.inputCurve'),(sample+'.position',point+'.translate')))
        if index<len(keys)-1:
            aim=names['ArcAimMatrix']
            edges.extend(((point+'.worldMatrix[0]',aim+'.inputMatrix'),
                (_names(keys[index+1])['ArcFrame']+'.worldMatrix[0]',aim+'.primaryTargetMatrix'),
                (joint.path+'.worldMatrix[0]',aim+'.secondaryTargetMatrix'),
                (aim+'.outputMatrix',names['ArcLocalMM']+'.matrixIn[0]')))
            if (c.getAttr(aim+'.secondaryMode')!=2 or tuple(c.getAttr(aim+'.secondaryInputAxis')[0])!=(0.,1.,0.)
                    or tuple(c.getAttr(aim+'.secondaryTargetVector')[0])!=(0.,1.,0.)):
                raise FitSkeletonValidationError('来源 Spline 原版 AimMatrix 常量被修改')
        edges.extend(((plan.scale_reference+'.worldInverseMatrix[0]',names['ArcLocalMM']+'.matrixIn[1]'),
            (names['ArcLocalMM']+'.matrixSum',names['ArcLocalPM']+'.inputMatrix'),
            (names['ArcLocalPM']+'.outputMatrix',names['ArcWorldMM']+'.matrixIn[0]'),
            (plan.scale_reference+'.worldMatrix[0]',names['ArcWorldMM']+'.matrixIn[1]'),
            (names['ArcWorldMM']+'.matrixSum',arc+'.offsetParentMatrix')))
        if c.getAttr(names['ArcLocalPM']+'.useScale') or c.getAttr(names['ArcLocalPM']+'.useShear'):
            raise FitSkeletonValidationError('来源 Spline IKAc 旋转必须在 Main 局部空间分解')
        for kind,source in (('SpFollowMM',joint.path),('AcFollowMM',arc)):
            matrix=names[kind]
            if not c.getAttr(matrix+'.advPySplineSourceBind',lock=True):
                raise FitSkeletonValidationError('来源 Spline FollowOffset 绑定矩阵已解锁')
            if (not c.getAttr(matrix+'.advPySplineSourceBindRecord',lock=True)
                    or tuple(json.loads(c.getAttr(matrix+'.advPySplineSourceBindRecord')))!=tuple(c.getAttr(matrix+'.advPySplineSourceBind'))):
                raise FitSkeletonValidationError('来源 Spline FollowOffset 绑定矩阵记录变化')
            edges.extend(((matrix+'.advPySplineSourceBind',matrix+'.matrixIn[0]'),(source+'.worldMatrix[0]',matrix+'.matrixIn[1]')))
        pick=names['AcFollowPM'];blend=names['OutputBM']
        if c.getAttr(pick+'.useScale') or c.getAttr(pick+'.useShear'):
            raise FitSkeletonValidationError('来源 Spline IKAc 必须剔除缩放和剪切')
        edges.extend(((names['AcFollowMM']+'.matrixSum',pick+'.inputMatrix'),
            (names['SpFollowMM']+'.matrixSum',blend+'.inputMatrix'),
            (plan.scale_reference+'.worldInverseMatrix[0]',names['AcFollowMM']+'.matrixIn[2]'),
            (pick+'.outputMatrix',names['AcFollowWorldMM']+'.matrixIn[0]'),
            (plan.scale_reference+'.worldMatrix[0]',names['AcFollowWorldMM']+'.matrixIn[1]'),
            (names['AcFollowWorldMM']+'.matrixSum',blend+'.target[0].targetMatrix'),
            ('AdvPy_SplineStretchUnit.output' if index==len(keys)-1 else 'AdvPy_SplineStretchEvenWeight.outputX',blend+'.target[0].weight'),
            (blend+'.outputMatrix',output+'.offsetParentMatrix')))
    for joint in ik:
        frame='AdvPy_'+joint.source_joint.rsplit('|',1)[-1]+'_SplineIKFrame'
        if c.objExists(frame):
            if (not c.getAttr(frame+'.advPySplineRestLocal',lock=True)
                    or any(abs(a-b)>1e-8 for a,b in zip(json.loads(c.getAttr(frame+'.advPySplineRestLocal')),c.getAttr(frame+'.matrix')))):
                raise FitSkeletonValidationError('来源 Spline Part 绑定补偿层被修改')
    end=plan.driver_targets[-1]+f'|AdvPy_SplineIKLocalOrient{len(plan.targets)-1}'
    edges.extend(((end+'.worldMatrix[0]','AdvPy_SplineIKArcEndRotation.inputMatrix'),
        (_names(keys[-1])['ArcPoint']+'.worldMatrix[0]','AdvPy_SplineIKArcEndPosition.inputMatrix'),
        ('AdvPy_SplineIKArcEndRotation.outputMatrix','AdvPy_SplineIKArcEndMatrix.matrixIn[0]'),
        ('AdvPy_SplineIKArcEndPosition.outputMatrix','AdvPy_SplineIKArcEndMatrix.matrixIn[1]'),
        ('AdvPy_SplineIKArcEndMatrix.matrixSum',_names(keys[-1])['ArcLocalMM']+'.matrixIn[0]')))
    for name,attrs in (('AdvPy_SplineIKArcEndRotation',('useTranslate','useScale','useShear')),
                       ('AdvPy_SplineIKArcEndPosition',('useRotate','useScale','useShear'))):
        if any(c.getAttr(name+'.'+attr) for attr in attrs):raise FitSkeletonValidationError('来源 Spline 末端矩阵过滤被修改')
    bad=[pair for pair in edges if not c.isConnected(*pair)]
    if bad:raise FitSkeletonValidationError('来源 Spline 原版双链矩阵接线被替换：'+repr(bad[:2]))


def _arc_world(c,plan,names,source):
    """Original IKAc: decompose world aim in its scaled parent's space."""
    local=c.createNode('multMatrix',name=names['ArcLocalMM'],skipSelect=True)
    pick=c.createNode('pickMatrix',name=names['ArcLocalPM'],skipSelect=True)
    world=c.createNode('multMatrix',name=names['ArcWorldMM'],skipSelect=True)
    c.connectAttr(source,local+'.matrixIn[0]')
    c.connectAttr(plan.scale_reference+'.worldInverseMatrix[0]',local+'.matrixIn[1]')
    c.connectAttr(local+'.matrixSum',pick+'.inputMatrix')
    c.setAttr(pick+'.useScale',False);c.setAttr(pick+'.useShear',False)
    c.connectAttr(pick+'.outputMatrix',world+'.matrixIn[0]')
    c.connectAttr(plan.scale_reference+'.worldMatrix[0]',world+'.matrixIn[1]')
    c.connectAttr(world+'.matrixSum',names['ArcFrame']+'.offsetParentMatrix')
