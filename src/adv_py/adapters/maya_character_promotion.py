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
    retained_paths={fit,*[row.path for row in staged.original.extensions],*(
        shape.rsplit('|',1)[0]
        for skin in staged.original.skins for shape,_,_ in skin.meshes)}
    retained_physical={
        (c.ls(host.scene_address(path),long=True) or
         [host.scene_address(path)])[0]
        for path in retained_paths}
    retained_mesh_paths={
        node for skin in staged.original.skins for shape,_,_ in skin.meshes
        for node in (shape,shape.rsplit('|',1)[0])}
    retained_mesh_physical={
        (c.ls(host.scene_address(path),long=True) or
         [host.scene_address(path)])[0]
        for path in retained_mesh_paths}
    replacement_by_role={role:new for role,_,new,_ in rows}
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
                if logical=='AllSet' and physical in retained_mesh_physical:
                    continue
                if physical.lstrip(':') in shared:continue
                raise CharacterRegistryError('旧 Rig 仍连接到保留边界之外：'+plug)
        if 'dagNode' in (c.nodeType(node,inherited=True) or []):
            children=c.listRelatives(node,children=True,fullPath=True) or []
            if any(child not in old_paths and child not in retained_physical
                   for child in children):
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
    retained=[]
    for logical in sorted(retained_paths,key=lambda path:(path.count('|'),path)):
        node=host.scene_address(logical)
        matches=c.ls(node,long=True) or []
        if len(matches)!=1:
            raise CharacterRegistryError('保留的 DAG 节点缺失：'+logical)
        parent=(c.listRelatives(matches[0],parent=True,fullPath=True) or [None])[0]
        if parent not in old_paths:
            continue
        role=host._cmds.identity.to_local(parent)
        if role not in replacement_by_role:
            raise CharacterRegistryError('保留节点的旧父级没有替换节点：'+logical)
        if c.nodeType(matches[0]) not in ('transform','joint'):
            raise CharacterRegistryError('保留的非变换 DAG 子节点需要专门迁移：'+logical)
        retained.append((c.ls(matches[0],uuid=True)[0],role,logical))
    host._transaction_changed=True
    retained_allset_ids=set()
    old_allset=host.scene_address('AllSet')
    new_allset=target.scene_address('AllSet')
    if bool(c.objExists(old_allset)) != bool(c.objExists(new_allset)):
        raise CharacterRegistryError('重建新旧 AllSet 结构不一致')
    if c.objExists(old_allset) and c.objExists(new_allset):
        members=[]
        for member in c.sets(old_allset,q=True) or []:
            paths=c.ls(member,long=True) or []
            if len(paths)==1 and paths[0] in retained_mesh_physical:
                members.append(paths[0])
                retained_allset_ids.add(c.ls(paths[0],uuid=True)[0])
        if members:
            c.sets(tuple(members),add=new_allset)
    c.delete(target.scene_address(fit))
    for uuid,_,_ in retained:
        c.parent(_by_uuid(c,uuid),world=True)
    c.delete(sorted(old_paths,key=lambda node:node.count('|'),reverse=True))
    # Maya may rename child shapes with their transform. Explicit UUID-based
    # renaming with ignoreShape keeps every shape role under our control.
    for uuid,name in rename:
        c.rename(_by_uuid(c,uuid),':'+name.lstrip(':'),ignoreShape=True)
    for uuid,role,logical in retained:
        c.parent(_by_uuid(c,uuid),_by_uuid(c,replacement_by_role[role]))
        if host._cmds.identity.to_local(_by_uuid(c,uuid))!=logical:
            raise CharacterRegistryError('保留 DAG 节点挂回后路径漂移：'+logical)
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
    remaining=c.namespaceInfo(staged.namespace,listOnlyDependencyNodes=True,recurse=True) or []
    if remaining:raise CharacterRegistryError('暂存命名空间仍有未归属节点：'+repr(remaining[:5]))
    c.namespace(removeNamespace=staged.namespace)
    promoted=replace(staged,namespace=host.namespace,registration=registration)
    if retained_allset_ids:
        final_allset=host.scene_address('AllSet')
        actual={c.ls(member,uuid=True)[0]
                for member in c.sets(final_allset,q=True) or []}
        if not retained_allset_ids<=actual:
            raise RuntimeError('重建交接丢失 AllSet 中保留的网格成员')
    if host.read_character_registration()!=registration:
        raise RuntimeError('原位替换后的角色登记复检失败')
    host.verify_character_retained_data(promoted)
    c.select([_by_uuid(c,uuid)+component for uuid,component in selection],replace=True) if selection else c.select(clear=True)
    return promoted
