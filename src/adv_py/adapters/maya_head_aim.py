"""Native aim and quaternion orientation blend; no expressions or callbacks."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.character_registry import safe_json,canonical,vector,CharacterRegistryError


def audit_registered(host,registration):
    channels=[ch for ch in registration.channels if ch.key.startswith('head.aim.')]
    if not channels:return
    expected={'head.aim.headAim',*('head.aim.target.'+kind+axis for kind in ('translate','rotate') for axis in 'XYZ')}
    if len(channels)!=7 or {ch.key for ch in channels}!=expected:raise CharacterRegistryError('头部瞄准通道声明不完整')
    audit(host,next(ch.node for ch in channels if ch.key=='head.aim.headAim'),
        next(ch.node for ch in channels if ch.key=='head.aim.target.translateX'))


def create(host,plan):
    c=host._cmds
    host._require_transaction();host._transaction_changed=True
    for name in (plan.rest,plan.solved):
        c.createNode('transform',name=name.rsplit('|',1)[-1],parent=plan.offset,skipSelect=True)
    c.createNode('transform',name='AdvPy_HeadAimOffset',parent=plan.target_offset.rsplit('|',1)[0],skipSelect=True)
    matrix=tuple(v for axis in plan.axes for v in (*axis,0.))+(*plan.position,1.)
    c.xform(plan.target_offset,ws=True,matrix=matrix)
    node=c.circle(name='AdvPy_HeadAim',normal=(1.,0.,0.),radius=plan.radius,constructionHistory=False)[0]
    c.parent(node,plan.target_offset,relative=True)
    for axis in 'XYZ':c.setAttr(plan.target+'.scale'+axis,lock=True,keyable=False)
    c.addAttr(plan.head_control,longName='headAim',niceName='瞄准权重',attributeType='double',defaultValue=0.,minValue=0.,maxValue=1.,keyable=True)
    c.aimConstraint(plan.target,plan.solved,name='AdvPy_HeadAimConstraint',aimVector=plan.aim_axis,upVector=plan.up_axis,
        worldUpType='objectrotation',worldUpVector=plan.up_axis,worldUpObject=plan.target,maintainOffset=False)
    c.addAttr('AdvPy_HeadAimConstraint',longName='advPyHeadAimAxes',dataType='string')
    c.setAttr('AdvPy_HeadAimConstraint.advPyHeadAimAxes',canonical({'format':'adv_py.head_aim.v1','aim':plan.aim_axis,'up':plan.up_axis}),type='string',lock=True)
    c.orientConstraint(plan.rest,plan.solved,plan.pivot,name='AdvPy_HeadAimOrient',maintainOffset=False)
    c.setAttr('AdvPy_HeadAimOrient.interpType',2)
    aliases=c.orientConstraint('AdvPy_HeadAimOrient',q=True,weightAliasList=True)
    c.createNode('reverse',name='AdvPy_HeadAimReverse',skipSelect=True)
    c.connectAttr(plan.head_control+'.headAim','AdvPy_HeadAimReverse.inputX')
    c.connectAttr('AdvPy_HeadAimReverse.outputX','AdvPy_HeadAimOrient.'+aliases[0])
    c.connectAttr(plan.head_control+'.headAim','AdvPy_HeadAimOrient.'+aliases[1])
    audit(host,plan.head_control,plan.target)


def audit(host,head_control,target):
    c=host._cmds
    pivot=head_control.rsplit('|',1)[0];offset=pivot.rsplit('|',1)[0]
    rest=offset+'|AdvPy_HeadAimRest';solved=offset+'|AdvPy_HeadAimSolved'
    for name,kind in (('AdvPy_HeadAimConstraint','aimConstraint'),('AdvPy_HeadAimOrient','orientConstraint'),('AdvPy_HeadAimReverse','reverse')):
        if not c.objExists(name) or c.nodeType(name)!=kind:raise FitSkeletonValidationError('头部瞄准节点缺失或类型错误：'+name)
    resolve=host._resolve_connected_node
    if (tuple(resolve(n) for n in c.orientConstraint('AdvPy_HeadAimOrient',q=True,targetList=True))!=(rest,solved)
            or tuple(resolve(n) for n in c.aimConstraint('AdvPy_HeadAimConstraint',q=True,targetList=True))!=(target,)):
        raise FitSkeletonValidationError('头部瞄准目标连接被替换')
    aliases=c.orientConstraint('AdvPy_HeadAimOrient',q=True,weightAliasList=True)
    edges=[(head_control+'.headAim','AdvPy_HeadAimReverse.inputX'),
        ('AdvPy_HeadAimReverse.outputX','AdvPy_HeadAimOrient.'+aliases[0]),
        (head_control+'.headAim','AdvPy_HeadAimOrient.'+aliases[1]),
        (target+'.worldMatrix[0]','AdvPy_HeadAimConstraint.worldUpMatrix')]
    edges += [('AdvPy_HeadAimOrient.constraintRotate'+axis,pivot+'.rotate'+axis) for axis in 'XYZ']
    edges += [('AdvPy_HeadAimConstraint.constraintRotate'+axis,solved+'.rotate'+axis) for axis in 'XYZ']
    if any(not c.isConnected(a,b) for a,b in edges):raise FitSkeletonValidationError('头部瞄准驱动连接不完整')
    metadata='AdvPy_HeadAimConstraint.advPyHeadAimAxes'
    if not c.objExists(metadata) or not c.getAttr(metadata,lock=True):raise FitSkeletonValidationError('头部瞄准轴记录缺失或未锁定')
    axes=safe_json(c.getAttr(metadata))
    if set(axes)!={'format','aim','up'} or axes['format']!='adv_py.head_aim.v1':raise FitSkeletonValidationError('头部瞄准轴记录格式无效')
    aim=vector(axes['aim'],3);up=vector(axes['up'],3)
    if any(abs(sum(v*v for v in a)-1.)>1e-6 for a in (aim,up)) or abs(sum(a*b for a,b in zip(aim,up)))>1e-6:
        raise FitSkeletonValidationError('头部瞄准轴必须正交且为单位向量')
    for attribute,value in (('aimVector',aim),('upVector',up),('worldUpVector',up),('offset',(0.,0.,0.))):
        if any(abs(a-b)>1e-8 for a,b in zip(c.getAttr('AdvPy_HeadAimConstraint.'+attribute)[0],value)):
            raise FitSkeletonValidationError('头部瞄准轴配置被修改：'+attribute)
    if c.getAttr('AdvPy_HeadAimConstraint.worldUpType')!=2 or c.getAttr('AdvPy_HeadAimOrient.interpType')!=2:
        raise FitSkeletonValidationError('头部瞄准求解模式被修改')
    for node in (rest,solved,pivot):
        if (tuple(c.getAttr(node+'.translate')[0])!=(0.,0.,0.) or tuple(c.getAttr(node+'.scale')[0])!=(1.,1.,1.)):
            raise FitSkeletonValidationError('头部瞄准参考层变换被修改：'+node)
    if tuple(c.getAttr(rest+'.rotate')[0])!=(0.,0.,0.):raise FitSkeletonValidationError('头部 FK 参考方向被修改')
    if c.getAttr(head_control+'.headAim',time=c.currentTime(q=True))>1e-8:
        origin=c.xform(pivot,q=True,ws=True,t=True);goal=c.xform(target,q=True,ws=True,t=True)
        direction=tuple(b-a for a,b in zip(origin,goal));length=sum(v*v for v in direction)**.5
        matrix=c.xform(target,q=True,ws=True,matrix=True)
        world_up=tuple(sum(up[i]*matrix[4*i+j] for i in range(3)) for j in range(3));up_length=sum(v*v for v in world_up)**.5
        if length<1e-5 or up_length<1e-8 or abs(sum(a*b for a,b in zip(direction,world_up)))/(length*up_length)>1.-1e-8:
            raise FitSkeletonValidationError('头部瞄准目标重合或与上方向平行，无法确定旋转')
