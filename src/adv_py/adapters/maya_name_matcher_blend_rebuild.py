"""Rebuild existing CreateBSControl nodes before retained property handoff.

The original circle and Head constraints are recreated in the stage. External
blendShape weights and animation remain on the original rig until the ordinary
audited handoff; this operation never force-connects production deformation.
"""
from dataclasses import dataclass,replace

from adv_py.core.character_registry import CharacterRegistryError,REGISTRY_NAME,encode_registration
from adv_py.core.character_body_retirement import complete_body_bindings
from .maya_character_body_retirement import is_connected_or_retired
from .maya_original_transform_channels import lock_original_transform_channels
from .maya_game_registration import scene_ids,remember_generated_nodes,_write_members
from .maya_driving_registration import _write_string


@dataclass(frozen=True)
class BlendConstraint:
    path: str
    uuid: str
    kind: str
    values: tuple


@dataclass(frozen=True)
class BlendController:
    path: str
    uuid: str
    parent: str | None
    shape: str
    matrix: tuple[float,...]
    channels: tuple
    constraints: tuple[BlendConstraint,...]


def _flat(value):
    if isinstance(value,(tuple,list)):
        return tuple(number for item in value for number in _flat(item))
    return (value,)


def capture(host,registration):
    c=host._cmds
    paths=tuple(dict.fromkeys(channel.node for channel in registration.channels
        if channel.key.startswith('nameMatcher.blendShape.')))
    if not paths:return ()
    heads=tuple(row.path for row in complete_body_bindings(registration)
                if row.path.rsplit('|',1)[-1]=='Head_M')
    if len(heads)!=1:
        raise CharacterRegistryError('NameMatcher BlendShape 控制器缺少原 Head 对应')
    head=heads[0]
    identities={node.path:node.uuid for node in registration.nodes}
    retired_heads=tuple(row for row in registration.retired_body if row.path==head)
    head_ids=c.ls(head,uuid=True) or ()
    if head in identities:
        if head_ids!=[identities[head]]:
            raise CharacterRegistryError('NameMatcher BlendShape 控制器的原 Head 身份改变')
    elif (len(retired_heads)!=1 or head_ids
            or getattr(c,'raw',c).ls(retired_heads[0].uuid,long=True)):
        raise CharacterRegistryError('NameMatcher BlendShape 控制器缺少真实 Head 身份或删除记录')
    rows=[]
    for path in paths:
        ids=c.ls(path,uuid=True) or ()
        if len(ids)!=1 or ids[0]!=identities.get(path) or c.nodeType(path)!='transform':
            raise CharacterRegistryError('NameMatcher BlendShape 控制器身份改变：'+path)
        shapes=c.listRelatives(path,shapes=True,noIntermediate=True,type='nurbsCurve',fullPath=True) or ()
        if not shapes:
            raise CharacterRegistryError('NameMatcher BlendShape 控制器没有原生曲线形状')
        children=c.listRelatives(path,children=True,fullPath=True) or ()
        constraints=[]
        for node in children:
            kind=c.nodeType(node)
            if kind not in ('parentConstraint','scaleConstraint'):continue
            targets=getattr(c,kind)(node,query=True,targetList=True) or ()
            if targets:
                actual=tuple(match for target in targets for match in c.ls(target,long=True) or ())
                if actual!=(head,):
                    raise CharacterRegistryError('NameMatcher BlendShape 控制器的约束目标不是原 Head')
            else:
                # Deleting an unused Head can leave the same native cached
                # constraint inputs. Require actual captured deletion edges.
                attributes=('translate','rotate','parentMatrix[0]') if kind=='parentConstraint' else ('scale',)
                destinations=('targetTranslate','targetRotate','targetParentMatrix') if kind=='parentConstraint' else ('targetScale',)
                if not all(is_connected_or_retired(host,head+'.'+source,
                        node+'.target[0].'+destination)
                        for source,destination in zip(attributes,destinations)):
                    raise CharacterRegistryError('NameMatcher BlendShape 约束缺少真实 Head 删除记录')
            node_ids=c.ls(node,uuid=True) or ()
            if len(node_ids)!=1:
                raise CharacterRegistryError('NameMatcher BlendShape 约束身份不唯一')
            values=[]
            for attr in ('target[0].targetOffsetTranslate','target[0].targetOffsetRotate',
                         'target[0].targetOffsetScale','offset','restTranslate','restRotate','restScale',
                         'enableRestPosition','interpType','constraintScaleCompensate','nodeState'):
                plug=node+'.'+attr
                if not c.objExists(plug) or c.connectionInfo(plug,sourceFromDestination=True):continue
                values.append((attr,c.getAttr(plug,type=True),_flat(c.getAttr(plug))))
            constraints.append(BlendConstraint(node,node_ids[0],kind,tuple(values)))
        if len({row.kind for row in constraints})!=len(constraints):
            raise CharacterRegistryError('NameMatcher BlendShape 控制器有重复的 Head 约束')
        parents=c.listRelatives(path,parent=True,fullPath=True) or ()
        if len(parents)>1:
            raise CharacterRegistryError('NameMatcher BlendShape 控制器有多个实例父级')
        rows.append(BlendController(path,ids[0],parents[0] if parents else None,shapes[0],
            tuple(float(value) for value in c.xform(path,query=True,worldSpace=True,matrix=True)),
            tuple(channel for channel in registration.channels if channel.node==path),tuple(constraints)))
    return tuple(rows)


def restore(host,rows,registration):
    if not rows:return registration
    host._require_transaction()
    c=host._cmds
    before=scene_ids(host)
    channels=[]
    added=[]
    for row in rows:
        name=row.path.rsplit('|',1)[-1]
        if c.objExists(name):
            raise CharacterRegistryError('NameMatcher BlendShape 暂存控制器名称已占用：'+name)
        host._transaction_changed=True
        control=c.circle(name=name,center=(0,0,0),normal=(0,1,0),sweep=360,radius=1,
            degree=3,useTolerance=False,tolerance=.01,sections=8,constructionHistory=False)[0]
        if row.parent:
            if not c.objExists(row.parent):
                raise CharacterRegistryError('NameMatcher BlendShape 暂存缺少原控制器父级')
            control=c.parent(control,row.parent,absolute=True)[0]
        if (c.ls(control,long=True) or ())!=[row.path]:
            raise CharacterRegistryError('NameMatcher BlendShape 暂存控制器路径变化')
        shape=(c.listRelatives(control,shapes=True,type='nurbsCurve',fullPath=True) or [None])[0]
        if shape is None:raise CharacterRegistryError('NameMatcher BlendShape 暂存圆圈创建失败')
        expected=row.shape.rsplit('|',1)[-1]
        if shape.rsplit('|',1)[-1]!=expected:shape=c.rename(shape,expected)
        c.setAttr(shape+'.overrideEnabled',True)
        c.setAttr(shape+'.overrideColor',17)
        # Static native outputs can survive deletion without a remaining
        # constraint. Preserve their actual cached pose, not a new Head link.
        c.xform(control,worldSpace=True,matrix=row.matrix)
        for saved in row.constraints:
            if not c.objExists('Head_M'):
                raise CharacterRegistryError('NameMatcher BlendShape 暂存必须先创建完整 Head')
            node=getattr(c,saved.kind)('Head_M',control,name=saved.path.rsplit('|',1)[-1])[0]
            if (c.ls(node,long=True) or ())!=[saved.path]:
                raise CharacterRegistryError('NameMatcher BlendShape 暂存约束路径变化')
            for attr,datatype,value in saved.values:
                if len(value)==1:c.setAttr(node+'.'+attr,value[0])
                else:c.setAttr(node+'.'+attr,*value,type=datatype)
        lock_original_transform_channels(c,control,True,True,True,True)
        for channel in row.channels:
            c.addAttr(control,longName=channel.attribute,attributeType='double',keyable=True,
                softMinValue=0,hasSoftMinValue=True,softMaxValue=1,hasSoftMaxValue=True,defaultValue=0)
            channels.append(channel)
        added.append(host.capture_character_registration_node(row.path))
    remember_generated_nodes(host,before)
    updated=replace(registration,nodes=registration.nodes+tuple(added),
                    channels=registration.channels+tuple(channels))
    _write_members(host,updated.nodes)
    _write_string(c,REGISTRY_NAME+'.advPyRegistryDocument',encode_registration(updated))
    return updated
