"""Promote an audited replacement after retained data has been handed over."""
from dataclasses import replace

from adv_py.core.character_identity import SHARED_NODES
from adv_py.core.character_registry import CharacterRegistryError,REGISTRY_NAME,encode_registration
from .maya_character_preservation import connections
from .maya_character_transfer import _by_uuid,_curve_name


def promote(host,staged):
    host._require_transaction()
    if staged.ownership is None:raise CharacterRegistryError('原位替换必须具有暂存归属记录')
    from maya import cmds as c
    from .maya_body import MayaBodyBuildHost
    target=MayaBodyBuildHost(namespace=staged.namespace)
    host.verify_character_retained_data(staged)
    rows=staged.ownership.nodes
    old_ids={old for _,old,_,_ in rows}
    old_paths={_by_uuid(c,uuid) for uuid in old_ids}
    fit=staged.original.registration.container
    old_fit=host.scene_address(fit)
    shared={host.scene_address(name).lstrip(':') for name in SHARED_NODES}
    # After handoff, no preserved data may still depend on a deletion candidate.
    for node in old_paths:
        logical=host._cmds.identity.to_local(node)
        for a,b in connections(host,logical):
            for plug in (a,b):
                physical=host.scene_address(plug.split('.',1)[0])
                physical=(c.ls(physical,long=True) or [physical])[0]
                if physical in old_paths or physical==old_fit or physical.startswith(old_fit+'|'):
                    continue
                if physical.lstrip(':') in shared:continue
                raise CharacterRegistryError('旧 Rig 仍连接到保留边界之外：'+plug)
        if 'dagNode' in (c.nodeType(node,inherited=True) or []):
            children=c.listRelatives(node,children=True,fullPath=True) or []
            if any(child not in old_paths for child in children):
                raise CharacterRegistryError('旧 Rig 清理仍会影响用户子节点：'+node)
    rename=[];references={}
    for role,old,new,kind in rows:
        old_node=_by_uuid(c,old)
        rename.append((new,old_node.rsplit('|',1)[-1]))
        references[target._cmds.identity.to_local(_by_uuid(c,new))]=host._cmds.identity.to_local(old_node)
    for curve in staged.original.curves:
        name=host.scene_address(_curve_name(curve))
        if c.objExists(name) and (c.ls(name,uuid=True) or [None])[0] not in old_ids:
            raise CharacterRegistryError('原位动画曲线名称被占用：'+name)
        rename.append((curve.uuid,name.lstrip(':')))
    replacement_by_old={old:new for _,old,new,_ in rows}
    selection=[]
    for item in c.ls(sl=True,long=True) or []:
        node,separator,component=item.partition('.')
        uuid=c.ls(node,uuid=True)[0]
        selection.append((replacement_by_old.get(uuid,uuid),separator+component))
    host._transaction_changed=True
    c.delete(sorted(old_paths,key=lambda node:node.count('|'),reverse=True))
    # Maya may rename child shapes with their transform. Explicit UUID-based
    # renaming with ignoreShape keeps every shape role under our control.
    for uuid,name in rename:
        c.rename(_by_uuid(c,uuid),':'+name.lstrip(':'),ignoreShape=True)
    original_fit={n.path:n for n in staged.original.registration.nodes
                  if n.path==fit or n.path.startswith(fit+'|')}
    def redirect(plug):
        node,attribute=plug.split('.',1)
        return references.get(node,node)+'.'+attribute
    registration=replace(staged.registration,nodes=tuple(original_fit.get(n.path,
        replace(n,inputs=tuple((attribute,redirect(source)) for attribute,source in n.inputs)))
        for n in staged.registration.nodes))
    registry=host.scene_address(REGISTRY_NAME)
    c.setAttr(registry+'.members',lock=False)
    for index,member in enumerate(registration.nodes):
        if member.path not in original_fit:continue
        plug=registry+f'.members[{index}]'
        current=c.connectionInfo(plug,sourceFromDestination=True)
        if current:c.disconnectAttr(current,plug)
        c.connectAttr(host.scene_address(member.path)+'.message',plug)
    c.setAttr(registry+'.members',lock=True)
    c.setAttr(registry+'.advPyRegistryDocument',lock=False)
    c.setAttr(registry+'.advPyRegistryDocument',encode_registration(registration),type='string')
    c.setAttr(registry+'.advPyRegistryDocument',lock=True)
    c.delete(target.scene_address(fit))
    remaining=c.namespaceInfo(staged.namespace,listOnlyDependencyNodes=True,recurse=True) or []
    if remaining:raise CharacterRegistryError('暂存命名空间仍有未归属节点：'+repr(remaining[:5]))
    c.namespace(removeNamespace=staged.namespace)
    promoted=replace(staged,namespace=host.namespace,registration=registration)
    if host.read_character_registration()!=registration:
        raise RuntimeError('原位替换后的角色登记复检失败')
    host.verify_character_retained_data(promoted)
    c.select([_by_uuid(c,uuid)+component for uuid,component in selection],replace=True) if selection else c.select(clear=True)
    return promoted
