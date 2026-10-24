"""Old bendyJoints update in asBuildAdvancedSkeleton, MEL 78675–78708."""
from adv_py.core.fit_settings import FitSkeletonValidationError


def upgrade(host, container='FitSkeleton', *, answer=None):
    host._require_transaction()
    c=host._cmds
    raw=getattr(c,'raw',c)
    joints=tuple(c.listRelatives(container,allDescendents=True,type='joint',fullPath=True) or ())
    first=next((joint for joint in joints
        if c.attributeQuery('bendyJoints',node=joint,exists=True)
        and c.getAttr(joint+'.bendyJoints')),None)
    if first is None:
        return ()
    c.select(first,replace=True)
    raw.refresh()
    if answer is None:
        answer=raw.confirmDialog(title='检测到旧版 FitSkeleton',
            message='新版 AdvancedSkeleton 支持任意数量的 Bendy 控制器。\n\n更新 Fit 属性？',
            button=('是','否','取消'),defaultButton='是',cancelButton='取消',dismissString='取消')
    if answer in ('Cancel','取消'):
        raise FitSkeletonValidationError('已取消旧版 Bendy Fit 属性升级和绑定构建')
    if answer in ('No','否'):
        return ()
    if answer not in ('Yes','是'):
        raise ValueError('未知旧版 Bendy Fit 属性升级选择：'+str(answer))
    if raw.optionMenu('asAttributeType',query=True,exists=True):
        raw.optionMenu('asAttributeType',edit=True,value='twist/bendy')
    updated=[]
    for joint in joints:
        if not c.attributeQuery('bendyJoints',node=joint,exists=True):
            continue
        # Source reads fitJoints[i], not fitJoints[y]. All legacy entries use
        # the first enabled old joint's count; preserve that actual policy.
        count=c.getAttr(first+'.twistJoints')
        c.select(joint,replace=True)
        host._transaction_changed=True
        for name in ('twistJoints','bendyJoints','bendyCtrls','partControllers'):
            if c.attributeQuery(name,node=joint,exists=True):
                c.deleteAttr(joint+'.'+name)
        if c.attributeQuery('inbetweenJoints',node=joint,exists=True):
            raise FitSkeletonValidationError('不能混用 Twist 和 Inbetween 属性')
        c.addAttr(joint,longName='twistJoints',attributeType='long',minValue=0,defaultValue=2,keyable=True)
        c.addAttr(joint,longName='bendyCtrls',attributeType='long',minValue=0,defaultValue=0,keyable=True)
        c.setAttr(joint+'.twistJoints',count)
        c.setAttr(joint+'.bendyCtrls',1)
        updated.append(joint)
    print('// Fit Attributes updated.')
    return tuple(updated)
