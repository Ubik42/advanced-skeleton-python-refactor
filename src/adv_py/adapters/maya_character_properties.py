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
        for name,datatype,value,locked,keyable,metadata in attributes:
            if dict(metadata).get('parent'):
                raise CharacterRegistryError('控制器复合自定义属性需要完整父子定义迁移：'+row.path+'.'+name)
        plugs={row.path+'.'+a[0] for a in attributes}
        rows.append(replace(row,attributes=attributes,connections=tuple((a,b) for a,b in row.connections if a in plugs or b in plugs)))
    return tuple(rows)


def install(target,rows):
    c=target._cmds
    for row in rows:
        for name,datatype,value,locked,keyable,metadata in row.attributes:
            plug=row.path+'.'+name;meta=dict(metadata)
            if c.objExists(plug):raise CharacterRegistryError('目标用户属性已存在：'+plug)
            options={'longName':name,'niceName':meta['niceName'],'keyable':keyable}
            if datatype in ('string','matrix'):options['dataType']=datatype
            else:options['attributeType']=datatype
            if datatype=='enum':options['enumName']=meta['enum'][0]
            if meta.get('default'):options['defaultValue']=meta['default'][0]
            for source,flag in (('minimum','minValue'),('maximum','maxValue'),('softMin','softMinValue'),('softMax','softMaxValue')):
                if meta.get(source):options[flag]=meta[source][0]
            c.addAttr(row.path,**options)
            if datatype=='string':
                if value is not None:c.setAttr(plug,value,type='string')
            elif datatype=='matrix':c.setAttr(plug,*value,type='matrix')
            elif datatype!='message':c.setAttr(plug,value)
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
