"""Original rebuild Keep Lock/Hide and enabled transform-limit restoration."""
from adv_py.core.character_registry import CharacterRegistryError


def install(target,rows):
    c=target._cmds
    for row in rows:
        if not c.objExists(row.node):
            raise CharacterRegistryError('保留控制状态的目标不存在：'+row.node)
        for flag,values,enabled in row.limits:
            c.transformLimits(row.node,**{flag:values,'e'+flag:enabled})
        # MEL restores the restrictions explicitly authored in the old rig.
        # It does not unlock a new generated mechanism or expose its channels.
        for attribute,locked,keyable,visible in row.channels:
            plug=row.node+'.'+attribute
            if not keyable:c.setAttr(plug,keyable=False)
            if visible:c.setAttr(plug,channelBox=True)
            if locked:c.setAttr(plug,lock=True)


def verify(target,rows):
    c=target._cmds
    for row in rows:
        for attribute,locked,keyable,visible in row.channels:
            plug=row.node+'.'+attribute
            if (locked and not c.getAttr(plug,lock=True)
                    or not keyable and c.getAttr(plug,keyable=True)
                    or visible and not c.getAttr(plug,channelBox=True)):
                raise RuntimeError('重建丢失控制器锁定或显示设置：'+plug)
        for flag,values,enabled in row.limits:
            actual=tuple(float(value) for value in c.transformLimits(row.node,q=True,**{flag:True}))
            flags=tuple(bool(value) for value in c.transformLimits(row.node,q=True,**{'e'+flag:True}))
            if flags!=enabled or len(actual)!=2 or any(abs(a-b)>1e-8 for a,b in zip(actual,values)):
                raise RuntimeError('重建丢失变换限制：'+row.node+'.'+flag)
