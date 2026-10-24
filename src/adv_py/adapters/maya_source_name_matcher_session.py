"""Persist owned MoCap topology without changing original constraint behavior."""
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_name_matcher_session import (
    ATTRIBUTE, FORMAT, KINDS, decode_session, encode_session)
from .maya_driving_registration import _write_string


def _commands(host):
    return getattr(host._cmds, 'raw', host._cmds)


def session_group(host):
    """Find the one session whose recorded receivers belong to this character.

    During staged rebuild the retained group stays in the original namespace;
    its receivers move to the stage. The locked UUID document carries that
    handoff without manufacturing another group or changing MoCap targets.
    """
    c = _commands(host)
    address = host.scene_address('MoCapConstraints')
    if c.objExists(address):
        return _node(c, address)[0]
    identity = getattr(host._cmds, 'identity', None)
    if identity is None:
        return None
    matches = []
    for candidate in c.ls('*.' + ATTRIBUTE, objectsOnly=True, long=True,
                          recursive=True) or ():
        if not c.objExists(candidate + '.advPyNameMatcher'):
            continue
        saved = decode_session(c.getAttr(candidate + '.' + ATTRIBUTE))
        if all(identity.owns(row['path']) for row in saved['receivers']):
            matches.append(candidate)
    if len(set(matches)) > 1:
        raise CharacterRegistryError('同一角色有多个动捕会话交接记录')
    return matches[0] if matches else None


def _node(c, address):
    names = c.ls(address, long=True) or ()
    identities = c.ls(address, uuid=True) or ()
    if len(names) != 1 or len(identities) != 1:
        raise CharacterRegistryError('动捕节点地址或身份不唯一：' + address)
    return names[0], identities[0]


def _plug(c, address):
    node, attribute = address.split('.', 1)
    path, identity = _node(c, node)
    return path + '.' + _channel_attribute(attribute), identity


def _channel_attribute(attribute):
    """Canonicalize only known native compound/child channel spellings."""
    parent, separator, child = attribute.partition('.')
    if separator:
        for prefix in ('translate','rotate','constraintTranslate','constraintRotate',
                       'outTranslate','outRotate'):
            if parent == prefix and child in tuple(prefix+axis for axis in 'XYZ'):
                return child
        for channel in ('Translate','Rotate'):
            for index in ('1','2'):
                if parent == 'in'+channel+index and child in tuple(
                        'in'+channel+axis+index for axis in 'XYZ'):
                    return child
    return attribute


def _capture(c, address):
    path, identity = _node(c, address)
    kind = c.nodeType(path)
    if kind not in KINDS:
        raise CharacterRegistryError('动捕组存在非会话节点：' + path)
    parents = c.listRelatives(path, parent=True, fullPath=True) or ()
    parent = _node(c, parents[0])[1] if parents else None
    pairs = c.listConnections(path, source=True, destination=False,
                              plugs=True, connections=True) or ()
    if len(pairs)%2:raise CharacterRegistryError('动捕会话节点输入连接列表不完整：'+path)
    inputs = []
    for destination, source in zip(pairs[::2], pairs[1::2]):
        source, source_uuid = _plug(c, source)
        inputs.append(dict(destination=_channel_attribute(destination.split('.', 1)[1]),
                           source=source, source_uuid=source_uuid))
    return dict(path=path, uuid=identity, kind=kind, parent=parent,
                inputs=sorted(inputs, key=lambda row: row['destination']))


def remember(host, created):
    """Record exact native targets and outputs after Connect, before saving."""
    host._require_transaction()
    c = _commands(host)
    group, group_uuid = _node(c, host.scene_address('MoCapConstraints'))
    paths = list(c.listRelatives(group, allDescendents=True, fullPath=True) or ())
    paths.extend(node for _, point, orient in created for node in (point, orient) if node)
    nodes = {_node(c, node)[1]: _capture(c, node) for node in paths}
    output_constraints=sorted({_node(c,node)[1] for _,point,orient in created
                               for node in (point,orient) if node})
    receivers = []
    by_control={control:(point,orient) for control,point,orient in created}
    for control in dict.fromkeys(control for control, _, _ in created):
        path, identity = _node(c, control)
        inputs = []
        for attribute in tuple(kind + axis for kind in ('translate', 'rotate') for axis in 'XYZ'):
            source = c.connectionInfo(path + '.' + attribute, sourceFromDestination=True)
            if not source:
                continue
            source, source_uuid = _plug(c, source)
            if c.nodeType(source.split('.',1)[0])=='pairBlend' and source_uuid not in nodes:
                nodes[source_uuid]=_capture(c,source.split('.',1)[0])
            if source_uuid in nodes:
                constraint=by_control[control][0 if attribute.startswith('translate') else 1]
                if not constraint:raise CharacterRegistryError('动捕接收通道没有原输出约束')
                inputs.append(dict(destination=attribute, source=source, source_uuid=source_uuid,
                                   constraint_uuid=_node(c,constraint)[1]))
        if inputs:
            receivers.append(dict(path=path, uuid=identity, inputs=inputs))
    value = dict(format=FORMAT, version=2, group=dict(path=group, uuid=group_uuid),
        nodes=sorted(nodes.values(), key=lambda row: row['path']), receivers=receivers,
        output_constraints=output_constraints,baked=False,removed_blends=[])
    if not c.objExists(group + '.' + ATTRIBUTE):
        c.addAttr(group, longName=ATTRIBUTE, dataType='string')
    _write_string(c, group + '.' + ATTRIBUTE, encode_session(value))
    c.setAttr(group + '.' + ATTRIBUTE, lock=True)
    return value


def audit(host):
    """Return only currently connected, UUID-proven output edges.

    Native Bake may disconnect those outputs. Detached outputs must remain
    detached or be replaced by a time animation curve; any other driver is
    rejected by character channel validation. Targets and helper topology
    must retain their original identities even after baking.
    """
    c = _commands(host)
    group_address = session_group(host)
    if group_address is None:
        return frozenset()
    group, group_uuid = _node(c, group_address)
    document = group + '.' + ATTRIBUTE
    if (not c.objExists(document) or not c.getAttr(document, lock=True)
            or not c.objExists(group + '.advPyNameMatcher')
            or not c.getAttr(group + '.advPyNameMatcher')
            or not c.getAttr(group + '.advPyNameMatcher', lock=True)):
        raise CharacterRegistryError('动捕会话缺少锁定的所有权记录')
    saved = decode_session(c.getAttr(document))
    if saved['group'] != dict(path=group, uuid=group_uuid):
        raise CharacterRegistryError('动捕会话组已被替换或改名')
    for node in saved['nodes']:
        if node['uuid'] in saved.get('removed_blends',()):
            if c.objExists(node['path']) or c.ls(node['uuid'],long=True):
                raise CharacterRegistryError('烘焙删除的原 pairBlend 身份重新出现：'+node['path'])
            continue
        if _capture(c, node['path']) != node:
            raise CharacterRegistryError('动捕会话辅助节点、目标或接线变化：' + node['path'])
    # A node added beneath the session must not become a deletion passenger.
    descendants = c.listRelatives(group, allDescendents=True, fullPath=True) or ()
    owned = {row['uuid'] for row in saved['nodes']}
    if any(_node(c, node)[1] not in owned for node in descendants):
        raise CharacterRegistryError('动捕会话组中加入了未登记节点')
    expected_outputs = (set(saved['output_constraints']) if saved['version']>=2 else
        {edge['source_uuid'] for receiver in saved['receivers'] for edge in receiver['inputs']})
    actual_outputs = set()
    for destination in c.listConnections(group + '.disableConstraints',
            source=False, destination=True, plugs=True) or ():
        destination, target_uuid = _plug(c,destination)
        if destination.split('.',1)[1] != 'nodeState':
            raise CharacterRegistryError('动捕禁用开关接到了其他属性')
        actual_outputs.add(target_uuid)
    if actual_outputs != expected_outputs:
        raise CharacterRegistryError('动捕禁用开关约束集合变化')
    allowed = set()
    receivers = {}
    for receiver in saved['receivers']:
        if _node(c, receiver['path']) != (receiver['path'], receiver['uuid']):
            raise CharacterRegistryError('动捕会话接收控制器被替换')
        for edge in receiver['inputs']:
            destination = receiver['path'] + '.' + edge['destination']
            receivers[destination] = edge
            source = c.connectionInfo(destination, sourceFromDestination=True)
            if source and _plug(c, source) == (edge['source'], edge['source_uuid']):
                allowed.add((receiver['uuid'], edge['destination'], edge['source_uuid'],
                             edge['source'].split('.', 1)[1]))
    for node in saved['nodes']:
        if node['uuid'] in saved.get('removed_blends',()):continue
        output = {'pointConstraint': 'constraintTranslate',
                  'orientConstraint': 'constraintRotate'}.get(node['kind'])
        outputs=(output,) if output else ('outTranslate','outRotate') if node['kind']=='pairBlend' else ()
        if not outputs:
            continue
        for output,axis in ((output,axis) for output in outputs for axis in 'XYZ'):
            source = node['path'] + '.' + output + axis
            for destination in c.listConnections(source, source=False,
                    destination=True, plugs=True) or ():
                destination, _ = _plug(c, destination)
                edge = receivers.get(destination)
                # Internal Pole helper outputs are protected by _capture.
                target_uuid = _node(c, destination.split('.', 1)[0])[1]
                if target_uuid in owned:
                    continue
                if edge is None or _plug(c, edge['source']) != _plug(c, source):
                    raise CharacterRegistryError('动捕会话约束被接到未登记控制器')
    return frozenset(allowed)


def remember_native_bake(host, *, mark_baked=True):
    """Observe Maya's native pairBlend bake changes in the same transaction.

    Do not create, delete or rewire blend nodes here. Constraints and Pole
    helpers keep their recorded identities; only generated pairBlends may
    disappear or receive native baked animation inputs.
    """
    host._require_transaction();c=_commands(host)
    group_address=session_group(host)
    if group_address is None:raise CharacterRegistryError('动捕烘焙缺少当前会话')
    group,_=_node(c,group_address)
    plug=group+'.'+ATTRIBUTE
    saved=decode_session(c.getAttr(plug))
    if saved['version']==1:return
    refreshed=[];removed=[]
    for row in saved['nodes']:
        if row['kind']!='pairBlend':
            if _capture(c,row['path'])!=row:
                raise CharacterRegistryError('动捕烘焙改变原约束或辅助节点：'+row['path'])
            refreshed.append(row);continue
        matches=c.ls(row['uuid'],long=True) or ()
        if not matches:
            if c.objExists(row['path']):raise CharacterRegistryError('烘焙时原 pairBlend 被同名节点替换')
            removed.append(row['uuid']);refreshed.append(row);continue
        current=_capture(c,row['path'])
        if any(current[key]!=row[key] for key in ('path','uuid','kind','parent')):
            raise CharacterRegistryError('烘焙时原 pairBlend 身份或父级变化')
        for edge in current['inputs']:
            if edge in row['inputs']:continue
            source=edge['source'].split('.',1)[0]
            if not c.nodeType(source).startswith('animCurve'):
                raise CharacterRegistryError('动捕烘焙给 pairBlend 增加了非动画来源')
        refreshed.append(current)
    updated={**saved,'nodes':refreshed,'baked':True if mark_baked else saved['baked'],'removed_blends':removed}
    _write_string(c,plug,encode_session(updated));c.setAttr(plug,lock=True)
    audit(host)


def allowed_input(host, allowed, node_uuid, attribute, source):
    if not allowed:
        return False
    physical = host.scene_address(source)
    node, output = physical.split('.', 1)
    _, identity = _node(_commands(host), node)
    return (node_uuid, attribute, identity, output) in allowed
