"""Observe the original temporary QuickIK graph; never change its drivers.

The Python registry must accept the exact constraints created by asQuickIK,
without accepting arbitrary replacement inputs on its editable FK controls.
"""
from adv_py.core.character_registry import CharacterRegistryError, canonical
from adv_py.core.source_quick_ik import ATTRIBUTE, FORMAT, decode_quick_ik as _decode
from adv_py.core.source_native_animation import ATTRIBUTE as NATIVE_ATTRIBUTE, FORMAT as NATIVE_FORMAT, encode_native_animation, decode_native_animation
from .maya_source_name_matcher_session import _commands, _node, _plug, _channel_attribute, _capture
from .maya_source_native_animation import _settings, _time_curve, verify_record
from .maya_driving_registration import _write_string



def _snapshot(c, address):
    path, identity = _node(c, address)
    pairs = c.listConnections(path, source=True, destination=False, plugs=True, connections=True) or ()
    if len(pairs) % 2:
        raise CharacterRegistryError('QuickIK 原生输入连接列表不完整')
    inputs = []
    for destination, source in zip(pairs[::2], pairs[1::2]):
        source, source_uuid = _plug(c, source)
        inputs.append(dict(destination=_channel_attribute(destination.split('.', 1)[1]), source=source, source_uuid=source_uuid))
    parents = c.listRelatives(path, parent=True, fullPath=True) or ()
    return dict(path=path, uuid=identity, kind=c.nodeType(path),
                parent=_node(c, parents[0])[1] if parents else None,
                inputs=sorted(inputs, key=lambda row: row['destination']))


def capture(host):
    c = _commands(host)
    if not c.objExists(host.scene_address('QuickIK')):
        return ()
    identity = getattr(host._cmds, 'identity', None)
    rows = []
    for group in c.ls('*.' + ATTRIBUTE, objectsOnly=True, long=True, recursive=True) or ():
        value = _decode(c.getAttr(group + '.' + ATTRIBUTE))
        if identity is not None and not identity.owns(group):
            continue
        if _node(c, group) != (value['group']['path'], value['group']['uuid']):
            raise CharacterRegistryError('QuickIK 图记录被复制到其他节点')
        _audit(c, value)
        rows.append(value)
    return tuple(rows)


def _audit(c, value):
    plug = value['group']['path'] + '.' + ATTRIBUTE
    if not c.getAttr(plug, lock=True) or _decode(c.getAttr(plug)) != value:
        raise CharacterRegistryError('QuickIK 图记录被改动或解锁')
    nodes = {row['uuid']: row for row in value['nodes']}
    for row in value.get('blend_settings',()):
        if _settings(c,nodes[row['uuid']]['path'])!=row['settings']:
            raise CharacterRegistryError('QuickIK 原生 pairBlend 缓存或混合设置变化')
    for row in value['nodes']:
        current = _snapshot(c, row['path'])
        if any(current[key] != row[key] for key in ('path', 'uuid', 'kind', 'parent')):
            raise CharacterRegistryError('QuickIK 原生图身份、父级或接线变化：' + row['path'])
        editable = row['kind'] in ('transform', 'joint') and row['path'].startswith(value['group']['path'] + '|')
        channels = tuple(kind + axis for kind in ('translate', 'rotate', 'scale') for axis in 'XYZ')
        for edge in current['inputs']:
            if edge in row['inputs']:
                continue
            if not (editable and edge['destination'] in channels and _time_curve(c, edge['source'])):
                raise CharacterRegistryError('QuickIK 原生图出现非原版动画输入：' + row['path'])
        for edge in row['inputs']:
            if edge not in current['inputs'] and not (editable and edge['destination'] in channels and _time_curve(c, edge['source'])):
                raise CharacterRegistryError('QuickIK 原生图原输入被删除：' + row['path'])
    allowed = set()
    destinations = {}
    for row in value['receivers']:
        if _node(c, row['path']) != (row['path'], row['uuid']):
            raise CharacterRegistryError('QuickIK 接收控制器身份变化')
        for edge in row['inputs']:
            destination = row['path'] + '.' + edge['destination']
            source = c.connectionInfo(destination, sourceFromDestination=True)
            if not source or _plug(c, source) != (edge['source'], edge['source_uuid']):
                raise CharacterRegistryError('QuickIK 接收控制器接线变化')
            driver = nodes[edge['source_uuid']]
            prefix = ('outTranslate' if edge['destination'].startswith('translate') else 'outRotate') if driver['kind'] == 'pairBlend' else 'constraintRotate'
            if (driver['kind'] != 'pairBlend' and (driver['uuid'] not in value['constraints'] or edge['destination'].startswith('translate'))
                    or _channel_attribute(edge['source'].split('.', 1)[1]) != prefix + edge['destination'][-1]):
                raise CharacterRegistryError('QuickIK 接收轴向与原创建约束不一致')
            destinations[destination] = edge
            allowed.add((row['uuid'], edge['destination'], edge['source_uuid'], edge['source'].split('.', 1)[1]))
    for row in value['nodes']:
        outputs = ('constraintRotate',) if row['uuid'] in value['constraints'] else ('outRotate', 'outTranslate') if row['kind'] == 'pairBlend' else ()
        for prefix in outputs:
            for axis in 'XYZ':
                source = row['path'] + '.' + prefix + axis
                for destination in c.listConnections(source, source=False, destination=True, plugs=True) or ():
                    destination, target = _plug(c, destination)
                    if target in nodes:
                        continue
                    edge = destinations.get(destination)
                    if edge is None or _plug(c, source) != (edge['source'], edge['source_uuid']):
                        raise CharacterRegistryError('QuickIK 被接到未登记的控制器')
    return frozenset(allowed)


def audit(host):
    c = _commands(host)
    return frozenset(edge for value in capture(host) for edge in _audit(c, value))


def remember(host, group, controls, constraints):
    host._require_transaction()
    c = _commands(host)
    group, identity = _node(c, host.scene_address(group))
    paths = (group, *(c.listRelatives(group, allDescendents=True, fullPath=True) or ()),
             *(host.scene_address(node) for node in constraints))
    nodes = {_node(c, path)[1]: _snapshot(c, path) for path in paths}
    outputs = tuple(_node(c, host.scene_address(path))[1] for path in constraints)
    receivers = []
    for control in controls:
        path, controller = _node(c, host.scene_address(control))
        inputs = []
        for attribute in tuple(kind + axis for kind in ('rotate', 'translate') for axis in 'XYZ'):
            source = c.connectionInfo(path + '.' + attribute, sourceFromDestination=True)
            if not source:
                continue
            source, source_uuid = _plug(c, source)
            source_node = source.split('.', 1)[0]
            if c.nodeType(source_node) == 'pairBlend':
                blend = _snapshot(c, source_node)
                if not any(edge['source_uuid'] in outputs for edge in blend['inputs']):
                    raise CharacterRegistryError('QuickIK 接收 pairBlend 没有原创建约束输入')
                nodes[source_uuid] = blend
            elif attribute.startswith('translate'):
                continue
            if source_uuid not in nodes:
                raise CharacterRegistryError('QuickIK 旋转通道未连接原创建约束')
            inputs.append(dict(destination=attribute, source=source, source_uuid=source_uuid))
        receivers.append(dict(path=path, uuid=controller, inputs=inputs))
    value = dict(format=FORMAT, version=2, group=dict(path=group, uuid=identity),
                 nodes=list(nodes.values()), constraints=list(outputs), receivers=receivers,
                 blend_settings=[dict(uuid=row['uuid'],settings=_settings(c,row['path']))
                                 for row in nodes.values() if row['kind']=='pairBlend'])
    plug = group + '.' + ATTRIBUTE
    c.addAttr(group, longName=ATTRIBUTE, dataType='string')
    _write_string(c, plug, canonical(value))
    c.setAttr(plug, lock=True)
    _audit(c, _decode(canonical(value)))
    return value


def finish_bake(host, records, controls):
    """After original bake+QuickIK deletion, observe Maya's surviving curves."""
    c = _commands(host)
    for value in records:
        if c.ls(value['group']['uuid'], long=True):
            raise CharacterRegistryError('QuickIK 原版清理后临时组仍存在')
        for row in value['nodes']:
            if row['kind'] != 'pairBlend':
                continue
            matches = c.ls(row['uuid'], long=True) or ()
            if not matches:
                if c.objExists(row['path']):
                    raise CharacterRegistryError('QuickIK 烘焙后原 pairBlend 被替换')
                continue
            current = _capture(c, matches[0])
            if any(current[key] != row[key] for key in ('path', 'uuid', 'kind', 'parent')):
                raise CharacterRegistryError('QuickIK 烘焙后原 pairBlend 身份变化')
            if any(edge not in row['inputs'] and not _time_curve(c, edge['source']) for edge in current['inputs']):
                raise CharacterRegistryError('QuickIK 烘焙后加入了非时间动画输入')
            receivers = []
            for old in value['receivers']:
                if _node(c, old['path']) != (old['path'], old['uuid']):
                    raise CharacterRegistryError('QuickIK 烘焙后控制器被替换')
                inputs = []
                for edge in old['inputs']:
                    source = c.connectionInfo(old['path'] + '.' + edge['destination'], sourceFromDestination=True)
                    if source and _plug(c, source)[1] == row['uuid']:
                        source, identity = _plug(c, source)
                        inputs.append(dict(destination=edge['destination'], source=source, source_uuid=identity))
                if inputs:
                    receivers.append(dict(path=old['path'], uuid=old['uuid'], inputs=inputs))
            if not receivers:
                continue
            plug = current['path'] + '.' + NATIVE_ATTRIBUTE
            origin = value['group']['uuid']
            if c.objExists(plug):
                previous = decode_native_animation(c.getAttr(plug))
                if previous['node']['uuid'] != current['uuid'] or not c.getAttr(plug, lock=True):
                    raise CharacterRegistryError('QuickIK 烘焙后的原生动画记录被替换或解锁')
                origin = previous['origin']
            document = dict(format=NATIVE_FORMAT, version=1, origin=origin,
                            node=current, settings=_settings(c, current['path']), receivers=receivers)
            if not c.objExists(plug):
                c.addAttr(current['path'], longName=NATIVE_ATTRIBUTE, dataType='string')
            _write_string(c, plug, encode_native_animation(document))
            c.setAttr(plug, lock=True)
            verify_record(host, document)
