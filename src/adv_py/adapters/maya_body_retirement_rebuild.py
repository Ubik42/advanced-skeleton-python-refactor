"""Reapply intentional native end deletion to a completely built replacement."""
from dataclasses import replace

from adv_py.core.character_body_retirement import retire_body_correspondence,frozen_origin
from adv_py.core.character_registry import CharacterRegistryError,REGISTRY_NAME,encode_registration
from .maya_character_body_retirement import capture,finish,audit,cached_value,cached_datatype,same_cached_value,array_element_exists
from .maya_game_registration import _write_members
from .maya_driving_registration import _write_string


def _native_delete_addresses(host, paths):
    """Use the actual MEL listRelatives addresses and traversal order."""
    c=host._cmds
    expected=set(paths)
    result=[]
    found=set()
    for address in c.listRelatives('DeformationSystem',allDescendents=True,type='joint') or ():
        matches=c.ls(address,long=True,type='joint') or ()
        if len(matches)!=1:
            raise CharacterRegistryError('原版末端遍历关节身份不唯一：'+address)
        if matches[0] in expected:
            result.append(address)
            found.add(matches[0])
    if found!=expected or len(result)!=len(expected):
        raise CharacterRegistryError('原版末端遍历未找到完整重建关节')
    return tuple(result)


def _retained_inputs(host, prior, generated, preservation):
    """Carry actual disconnected production inputs without touching their DG."""
    missing = tuple(item for item in prior.frozen_inputs
        if (item.source,item.destination) not in generated)
    if not missing:
        return ()
    if preservation is None:
        raise CharacterRegistryError('末端缓存输入交接缺少完整生产对象保留快照')
    c = host._cmds
    raw = getattr(c,'raw',c)
    ids = {row.uuid for row in (*preservation.skins,*preservation.extensions)}
    # Native bindPose sparse inputs can be cached by the same deletion.
    # Discover it through a retained Skin, not a guessed scene-wide name.
    for skin in preservation.skins:
        nodes = raw.ls(skin.uuid,long=True) or ()
        if len(nodes)!=1:
            raise CharacterRegistryError('末端缓存交接的保留 Skin 身份改变')
        for pose in raw.listConnections(nodes[0]+'.bindPose',source=True,destination=False) or ():
            if raw.nodeType(pose)=='dagPose':
                ids.update(raw.ls(pose,uuid=True) or ())
    result = []
    for item in missing:
        if item.destination_uuid not in ids:
            raise CharacterRegistryError('末端缓存目标既未重新生成，也不属于已保留对象：'+item.destination)
        nodes = raw.ls(item.destination_uuid,long=True) or ()
        if len(nodes)!=1:
            raise CharacterRegistryError('末端缓存交接的实际目标身份缺失或歧义')
        plug = nodes[0]+'.'+item.destination.split('.',1)[1]
        if not item.element_exists:
            if (array_element_exists(raw,plug) or cached_datatype(raw,plug)!=item.datatype
                    or raw.ls(frozen_origin(prior,item),long=True)):
                raise CharacterRegistryError('原版已删除数组元素的交接状态改变：'+plug)
            destination=c.identity.to_local(plug) if hasattr(c,'identity') else plug
            result.append(replace(item,destination=destination,source_uuid=frozen_origin(prior,item)))
            continue
        if not raw.objExists(plug):
            raise CharacterRegistryError('末端缓存交接的实际生产属性消失：'+plug)
        actual = cached_value(raw,plug,item.datatype)
        if (cached_datatype(raw,plug)!=item.datatype
                or raw.connectionInfo(plug,sourceFromDestination=True)
                or not same_cached_value(actual,item.value)
                or raw.ls(frozen_origin(prior,item),long=True)):
            raise CharacterRegistryError('末端缓存交接时实际生产输入状态改变：'+plug)
        # Explicit outsider addresses bypass the stage namespace. The same
        # original target UUID and old origin remain true after promotion.
        destination = c.identity.to_local(plug) if hasattr(c,'identity') else plug
        result.append(replace(item,destination=destination,
                              source_uuid=frozen_origin(prior,item)))
    return tuple(result)


def restore(host, original, *, preservation=None):
    """Delete the same Body identities only after all original graphs exist.

    Rebuild carries the surviving graph's cached values, not a shorter RP or
    Spline plan. Production Skin/foreign destinations are transferred by the
    ordinary character handoff, so they are not manufactured in the stage.
    """
    host._require_transaction()
    if not original.retired_body:return host.read_character_registration()
    current = host.read_character_registration()
    if current.retired_body:
        raise CharacterRegistryError('重建暂存角色已经有末端清理记录')
    c = host._cmds
    paths = tuple(row.path for row in original.retired_body)
    if not set(paths).issubset(joint.path for joint in current.body):
        raise CharacterRegistryError('重建暂存未生成原版已清理的完整 Body 末端')
    captured = capture(host,current,paths)
    host._transaction_changed = True
    # MEL 75611 uses listRelatives' shortest unique addresses, in its returned
    # order. Do not substitute full DAG paths or a different deletion order.
    for address in _native_delete_addresses(host,paths):c.delete(address)
    retired = finish(host,captured)
    originals = {row.path:row for row in original.retired_body}
    rewritten = []
    for row in retired:
        prior = originals[row.path]
        old_nodes = {(node.path,node.node_type) for node in prior.removed_nodes}
        new_nodes = {(node.path,node.node_type) for node in row.removed_nodes}
        if old_nodes != new_nodes:
            raise CharacterRegistryError('重建暂存的末端附属图与原版清理记录不同：'+row.path)
        if row.properties!=prior.properties:
            raise CharacterRegistryError('重建暂存的末端来源设置与删除前不同：'+row.path)
        old_inputs = {(item.source,item.destination):item for item in prior.frozen_inputs}
        frozen = []
        for item in row.frozen_inputs:
            previous = old_inputs.get((item.source,item.destination))
            if previous is None or previous.datatype!=item.datatype:
                raise CharacterRegistryError('重建暂存的末端保留输入没有原始清理记录：'+item.destination)
            if previous.element_exists!=item.element_exists:
                raise CharacterRegistryError('重建末端删除改变了原版数组元素的存在状态：'+item.destination)
            if previous.value is None:
                if item.value is not None:
                    raise CharacterRegistryError('重建末端删除未留下原版空矩阵槽：'+item.destination)
            elif item.datatype!='message':
                plug = item.destination
                locked = bool(c.getAttr(plug,lock=True))
                try:
                    if locked:c.setAttr(plug,lock=False)
                    if len(previous.value)==1:
                        c.setAttr(plug,previous.value[0])
                    else:
                        c.setAttr(plug,*previous.value,type=item.datatype)
                finally:
                    if locked:c.setAttr(plug,lock=True)
            frozen.append(replace(item,value=previous.value,
                                  source_uuid=frozen_origin(prior,previous)))
        frozen.extend(_retained_inputs(host,prior,
            {(item.source,item.destination) for item in row.frozen_inputs},preservation))
        rewritten.append(replace(row,frozen_inputs=tuple(frozen)))
    removed = set(paths)
    channels = tuple(channel for channel in current.channels if channel.node not in removed)
    user_plugs = {channel.node+'.'+channel.attribute for channel in channels}
    nodes = tuple(replace(node,inputs=tuple((attr,source) for attr,source in node.inputs
        if not (node.path+'.'+attr in user_plugs and host._character_direct_animation(source))))
        for node in (host.capture_character_registration_node(row.path)
                     for row in current.nodes if c.objExists(row.path)))
    updated = retire_body_correspondence(current,tuple(rewritten),nodes,channels)
    for owner in (current.body_root,current.container):
        plug = owner+'.advPyBodyJointCount'
        if c.objExists(plug):
            c.setAttr(plug,lock=False)
            c.setAttr(plug,len(updated.body),lock=True)
    _write_members(host,updated.nodes)
    _write_string(c,REGISTRY_NAME+'.advPyRegistryDocument',encode_registration(updated))
    audit(host,updated)
    if host.read_character_registration()!=updated:
        raise CharacterRegistryError('重建暂存的原版末端清理状态无法完整读回')
    return updated
