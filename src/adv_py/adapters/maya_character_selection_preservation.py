"""Preserve the native user selection sets supported by original MEL rebuild."""
from adv_py.core.character_preservation import PreservedSelectionSet
from adv_py.core.character_registry import CharacterRegistryError
from .maya_character_preservation import connections


_GENERATED_SETS=('AllSet','ControlSet','DeformSet','Sets')


def _members(c,node):
    result=set()
    for member in c.sets(node,q=True) or []:
        # Canonical individual component addresses avoid differences in
        # Maya's range compression after removing and adding members.
        for address in c.ls(member,long=True,flatten=True) or []:
            path,separator,component=address.partition('.')
            ids=c.ls(path,uuid=True) or []
            if len(ids)!=1:
                raise CharacterRegistryError('用户选择集成员身份不唯一：'+address)
            result.add((ids[0],separator+component))
    return tuple(sorted(result))


def _parents(c,node):
    return tuple(sorted({c.ls(parent,uuid=True)[0]
        for parent in c.listSets(object=node) or []
        if c.nodeType(parent)=='objectSet'}))


def capture(host,registration):
    from maya import cmds as c
    generated={host.scene_address(name).lstrip(':') for name in _GENERATED_SETS}
    nodes={host.scene_address(row.path) for row in registration.nodes
           if row.path!=registration.container
           and not row.path.startswith(registration.container+'|')}
    for name in ('AllSet','ControlSet','DeformSet'):
        if c.objExists(host.scene_address(name)):
            nodes.update(member.partition('.')[0]
                         for member in c.sets(host.scene_address(name),q=True) or [])
    for channel in registration.channels:
        nodes.update(c.listRelatives(host.scene_address(channel.node),shapes=True,fullPath=True) or [])
    candidates=set()
    for node in nodes:
        candidates.update(c.listSets(object=node) or [])
    rows=[]
    for node in sorted(candidates):
        if node.lstrip(':') in generated or c.nodeType(node)!='objectSet':continue
        if c.referenceQuery(node,isNodeReferenced=True) or any(c.lockNode(node,q=True,lock=True) or []):
            raise CharacterRegistryError('用户选择集被引用或锁定：'+node)
        logical=host._cmds.identity.to_local(node)
        links=tuple(edge for edge in connections(host,logical)
                    if membership_edge(edge))
        rows.append(PreservedSelectionSet(logical,c.ls(node,uuid=True)[0],
                                         _members(c,node),_parents(c,node),links))
    return tuple(sorted(rows,key=lambda row:row.uuid))


def membership_edge(edge):
    """Only native set-member links are exempt from rig graph equality."""
    source,destination=edge
    attribute=destination.split('.',1)[1]
    return attribute.startswith(('dagSetMembers[','dnSetMembers['))


def install(host,staged):
    from maya import cmds as c
    from .maya_character_transfer import _by_uuid
    ownership=staged.ownership
    replacements={old:new for _,old,new,_ in ownership.nodes}
    for row in staged.original.selection_sets:
        node=_by_uuid(c,row.uuid)
        if c.nodeType(node)!='objectSet':
            raise CharacterRegistryError('保留的用户选择集类型变化：'+row.node)
        for old_uuid,component in row.members:
            new_uuid=replacements.get(old_uuid)
            if new_uuid is None:continue
            source=_by_uuid(c,old_uuid)+component
            target=_by_uuid(c,new_uuid)+component
            if not c.sets(source,isMember=node):
                raise CharacterRegistryError('用户选择集在交接前发生变化：'+row.node)
            c.sets(source,remove=node)
            c.sets(target,add=node)
        for parent_uuid in row.parents:
            new_uuid=replacements.get(parent_uuid)
            if new_uuid is None:continue
            c.sets(node,remove=_by_uuid(c,parent_uuid))
            c.sets(node,add=_by_uuid(c,new_uuid))


def verify(staged):
    from maya import cmds as c
    from .maya_character_transfer import _by_uuid
    replacements={old:new for _,old,new,_ in staged.ownership.nodes}
    for row in staged.original.selection_sets:
        node=_by_uuid(c,row.uuid)
        expected=tuple(sorted((replacements.get(uuid,uuid),component)
                              for uuid,component in row.members))
        parents=tuple(sorted(replacements.get(uuid,uuid) for uuid in row.parents))
        if c.nodeType(node)!='objectSet' or _members(c,node)!=expected or _parents(c,node)!=parents:
            raise RuntimeError('重建改变了用户选择集身份、成员或父集：'+row.node)
