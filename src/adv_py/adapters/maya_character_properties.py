"""Copy explicit property definitions before migrating their native connections."""
from dataclasses import replace
from adv_py.core.character_registry import CharacterRegistryError
from .maya_character_preservation import capture_extension


def plan(host,original,namespace):
    from .maya_body import MayaBodyBuildHost
    target=MayaBodyBuildHost(namespace=namespace)
    c=target._cmds
    rows=[]
    for row in original.properties:
        attributes=tuple(a for a in row.attributes if not c.objExists(row.path+'.'+a[0]) and a[0]!='lockInfluenceWeights')
        if not attributes:continue
        pending={item[0] for item in attributes}
        for name,datatype,value,locked,keyable,metadata in attributes:
            parent=tuple(dict(metadata).get('parent') or ())
            if parent and parent[0] not in pending and not c.objExists(
                    row.path+'.'+parent[0]):
                raise CharacterRegistryError(
                    '控制器复合自定义属性缺少父级：'+row.path+'.'+name)
        plugs={row.path+'.'+a[0] for a in attributes}
        rows.append(replace(row,attributes=attributes,connections=tuple((a,b) for a,b in row.connections if a in plugs or b in plugs)))
    return tuple(rows)


def install(target,rows):
    c=target._cmds
    for row in rows:
        pending={item[0]:item for item in row.attributes}
        child_order={child:(item[0],index)
                     for item in row.attributes
                     for index,child in enumerate(
                         tuple(dict(item[5]).get('children') or ()))}
        ordered=[]
        while pending:
            ready=[item for item in pending.values()
                   if not (parent:=tuple(dict(item[5]).get('parent') or ()))
                   or parent[0] not in pending]
            if not ready:
                raise CharacterRegistryError(
                    '控制器复合自定义属性父链循环：'+row.path)
            for item in sorted(ready,key=lambda value:(
                    *child_order.get(value[0],('',0)),value[0])):
                ordered.append(item)
                del pending[item[0]]
        for name,datatype,value,locked,keyable,metadata in ordered:
            plug=row.path+'.'+name;meta=dict(metadata)
            if c.objExists(plug):raise CharacterRegistryError('目标用户属性已存在：'+plug)
            options={'longName':name,'niceName':meta['niceName'],'keyable':keyable}
            parent=tuple(meta.get('parent') or ())
            if parent:options['parent']=parent[0]
            if datatype in ('string','matrix'):options['dataType']=datatype
            else:options['attributeType']=datatype
            if datatype=='compound':
                options['numberOfChildren']=len(tuple(meta.get('children') or ()))
            if datatype=='enum':options['enumName']=meta['enum'][0]
            if meta.get('default'):options['defaultValue']=meta['default'][0]
            for source,flag in (('minimum','minValue'),('maximum','maxValue'),('softMin','softMinValue'),('softMax','softMaxValue')):
                if meta.get(source):options[flag]=meta[source][0]
            c.addAttr(row.path,**options)
            if datatype=='string':
                if value is not None:c.setAttr(plug,value,type='string')
            elif datatype=='matrix':c.setAttr(plug,*value,type='matrix')
            elif datatype!='message' and not meta.get('children'):
                c.setAttr(plug,value)
            if not keyable:c.setAttr(plug,channelBox=meta['channelBox'])
            # Locks are applied after connections are transferred.


def lock_and_verify(target,rows,*,apply_locks=False):
    c=target._cmds
    for row in rows:
        if apply_locks:
            for name,datatype,value,locked,keyable,metadata in row.attributes:
                c.setAttr(row.path+'.'+name,lock=locked)
        current=capture_extension(target,row.path)
        by_name={a[0]:a for a in current.attributes}
        for attribute in row.attributes:
            if by_name.get(attribute[0])!=attribute:
                raise RuntimeError('控制器用户属性定义或数值复检失败：'+row.path+'.'+attribute[0])
