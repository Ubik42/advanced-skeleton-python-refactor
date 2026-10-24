"""Closed provenance for Body tips removed by native export preparation.

This records what Maya's deletion did. It does not shorten a solver chain,
create replacement deform joints, or reconnect a deleted source.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class RetiredBodyInput:
    source: str
    destination: str
    destination_uuid: str
    datatype: str
    value: tuple[float, ...] | None
    # The value can outlive several rebuilds. Its physical origin is the
    # deleted node which produced it, never a newly generated namesake.
    source_uuid: str = ''
    element_exists: bool = True


@dataclass(frozen=True, slots=True)
class RetiredBodyGraphNode:
    path: str
    uuid: str
    node_type: str
    inputs: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CharacterRetiredBodyJoint:
    path: str
    uuid: str
    parent: str
    matrix: tuple[float, ...]
    rotate_order: int
    body_index: int
    frozen_inputs: tuple[RetiredBodyInput, ...] = ()
    incoming: tuple[tuple[str, str], ...] = ()
    removed_nodes: tuple[RetiredBodyGraphNode, ...] = ()
    records: tuple[tuple[str, str], ...] = ()
    properties: tuple[tuple[str, bool], ...] = ()


_VALUE_COUNTS = {
    'bool': 1, 'byte': 1, 'char': 1, 'short': 1, 'long': 1,
    'enum': 1, 'float': 1, 'double': 1, 'doubleAngle': 1, 'doubleLinear': 1,
    'short2': 2, 'long2': 2, 'float2': 2, 'double2': 2,
    'short3': 3, 'long3': 3, 'float3': 3, 'double3': 3,
    'matrix': 16, 'fltMatrix': 16,
    'message': 0,
}

_REMOVED_KINDS = frozenset(('pointConstraint','orientConstraint','parentConstraint','scaleConstraint'))
_SOURCE_RECORDS = frozenset(('advPySourceFkMatrix','advPySourceBendyMatrix',
    'advPySourceLocalScale','advPySourcePartPoint','advPySourceTwistPosition',
    'advPySourceInbetweenMatrix','advPySourceBodyMatrix','advPySourceEndMatrix'))
_SOURCE_PROPERTIES = frozenset(('advPySourceFkPoint','segmentScaleCompensate'))


def retirement_plug(value):
    """An exact local Maya plug, including array and compound attributes."""
    from .character_registry import CharacterRegistryError
    if not isinstance(value, str) or '.' not in value:
        raise CharacterRegistryError('末端清理记录端口无效')
    node, attribute = value.split('.', 1)
    if node.startswith('|') and ':' not in node:
        from .character_registry import path
        path(node)
    elif not re.fullmatch(r'(?:\|)?(?::)?[A-Za-z_][A-Za-z_0-9]*'
                          r'(?::[A-Za-z_][A-Za-z_0-9]*)*'
                          r'(?:\|(?::)?[A-Za-z_][A-Za-z_0-9]*(?::[A-Za-z_][A-Za-z_0-9]*)*)*', node):
        raise CharacterRegistryError('末端清理记录节点地址无效')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\[[0-9]+\])?'
                        r'(?:\.[A-Za-z_][A-Za-z_0-9]*(?:\[[0-9]+\])?)*', attribute):
        raise CharacterRegistryError('末端清理记录属性地址无效')
    return value


def canonical_retirement_channel(plug):
    """Maya compound/child spelling has no effect on a captured connection."""
    node,separator,attribute=plug.partition('.')
    if not separator:return plug
    parent,dot,child=attribute.partition('.')
    vectors=('translate','rotate','scale','inverseScale','jointOrient','rotateAxis',
             'constraintTranslate','constraintRotate','constraintScale',
             'outputTranslate','outputRotate','outputScale')
    if dot and parent in vectors and child in tuple(parent+axis for axis in 'XYZ'):
        return node+'.'+child
    return plug


def decode_retired_body(raw, body_root, body, nodes, *, historical_origins=False,
                       external_spline_spaces=None, array_presence=False):
    from .character_registry import exact, path, vector, CharacterRegistryError
    if not isinstance(raw, (list, tuple)) or len(raw) > 256:
        raise CharacterRegistryError('末端清理记录数量无效')
    if len(body) + len(raw) > 256:
        raise CharacterRegistryError('原 Body 与已清理末端的总数超出登记限制')
    live_nodes = {node.path for node in nodes}
    live_ids = {node.uuid for node in nodes}
    result = []
    destinations = set()
    removed_ids, removed_paths = set(), set()
    for row in raw:
        if isinstance(row,dict):
            row = dict(row)
            for optional in ('incoming','removed_nodes','records','properties'):
                row.setdefault(optional,[])
        exact(row, ('path','uuid','parent','matrix','rotate_order','body_index','frozen_inputs',
                    'incoming','removed_nodes','records','properties'))
        address = path(row['path'])
        parent = path(row['parent'])
        identity = row['uuid']
        order = row['rotate_order']
        index = row['body_index']
        if (not address.startswith(body_root + '|') or address in live_nodes
                or address.rsplit('|', 1)[0] != parent
                or not isinstance(identity, str) or not identity or identity in live_ids
                or type(order) is not int or not 0 <= order < 6
                or type(index) is not int or not 0 <= index < len(body) + len(raw)):
            raise CharacterRegistryError('已清理末端的身份、父级或旋转顺序无效')
        def incoming_edges(values, target):
            if not isinstance(values,(list,tuple)) or len(values)>4096:
                raise CharacterRegistryError('末端清理的原输入数量无效')
            edges,seen = [],set()
            for edge in values:
                if not isinstance(edge,(list,tuple)) or len(edge)!=2:
                    raise CharacterRegistryError('末端清理的原输入字段无效')
                source,destination = map(retirement_plug,edge)
                if destination.split('.',1)[0]!=target or destination in seen:
                    raise CharacterRegistryError('末端清理的原输入目标无效或重复')
                seen.add(destination)
                edges.append((source,destination))
            return tuple(edges)
        original_inputs = incoming_edges(row['incoming'],address)
        if not isinstance(row['removed_nodes'],(list,tuple)) or len(row['removed_nodes'])>64:
            raise CharacterRegistryError('末端清理的附属节点数量无效')
        removed = []
        spaces = (external_spline_spaces or {}).get(address,())
        for item in row['removed_nodes']:
            exact(item,('path','uuid','node_type','inputs'))
            child = path(item['path'])
            child_id = item['uuid']
            external_space = child in spaces and item['node_type']=='transform'
            external_constraint = (item['node_type'] in _REMOVED_KINDS
                                   and any(child.startswith(space+'|') for space in spaces))
            if (not (child.startswith(address+'|') or external_space or external_constraint)
                    or child in live_nodes|removed_paths
                    or not isinstance(item['node_type'],str)
                    or not (item['node_type'] in _REMOVED_KINDS or external_space)
                    or not isinstance(child_id,str) or not child_id
                    or child_id in live_ids|removed_ids or child_id==identity):
                raise CharacterRegistryError('末端清理的附属节点身份或归属无效')
            removed_ids.add(child_id)
            removed_paths.add(child)
            removed.append(RetiredBodyGraphNode(child,child_id,item['node_type'],
                                               incoming_edges(item['inputs'],child)))
        records, record_names = [],set()
        if not isinstance(row['records'],(list,tuple)) or len(row['records'])>len(_SOURCE_RECORDS):
            raise CharacterRegistryError('末端清理的来源图记录数量无效')
        from .character_registry import safe_json
        for item in row['records']:
            if (not isinstance(item,(list,tuple)) or len(item)!=2
                    or not isinstance(item[0],str) or item[0] not in _SOURCE_RECORDS or item[0] in record_names
                    or not isinstance(item[1],str)):
                raise CharacterRegistryError('末端清理的来源图记录字段无效')
            safe_json(item[1])
            record_names.add(item[0])
            records.append(tuple(item))
        properties = row['properties']
        if (not isinstance(properties,(list,tuple)) or len(properties)>len(_SOURCE_PROPERTIES)
                or any(not isinstance(item,(list,tuple)) or len(item)!=2
                       or not isinstance(item[0],str) or item[0] not in _SOURCE_PROPERTIES or type(item[1]) is not bool
                       for item in properties)
                or len({item[0] for item in properties})!=len(properties)):
            raise CharacterRegistryError('末端清理的来源设置字段无效或重复')
        if 'advPySourceFkMatrix' in record_names and 'advPySourceFkPoint' not in dict(properties):
            raise CharacterRegistryError('末端清理的 FK 矩阵缺少原位置接收设置')
        inputs = []
        if not isinstance(row['frozen_inputs'], (list, tuple)) or len(row['frozen_inputs']) > 4096:
            raise CharacterRegistryError('末端清理的保留输入数量无效')
        for item in row['frozen_inputs']:
            exact(item, ('source','destination','destination_uuid','datatype','value')
                  + (('source_uuid',) if historical_origins else ())
                  + (('element_exists',) if array_presence else ()))
            source = retirement_plug(item['source'])
            destination = retirement_plug(item['destination'])
            count = _VALUE_COUNTS.get(item['datatype']) if isinstance(item['datatype'],str) else None
            if (source.split('.', 1)[0] not in {address,*(node.path for node in removed)}
                    or destination in destinations
                    or count is None or not isinstance(item['destination_uuid'], str)
                    or not item['destination_uuid'] or item['destination_uuid'] == identity):
                raise CharacterRegistryError('末端清理的保留输入来源或身份无效')
            destinations.add(destination)
            origin = item.get('source_uuid', '')
            if (not isinstance(origin, str) or origin and (
                    origin in live_ids or origin == item['destination_uuid'])):
                raise CharacterRegistryError('末端缓存值的历史来源身份无效')
            exists=item.get('element_exists',True)
            if (type(exists) is not bool or not exists and (
                    item['value'] is not None or item['datatype']=='message'
                    or '[' not in destination.split('.',1)[1])):
                raise CharacterRegistryError('末端清理的数组元素缺失记录无效')
            value = (None if not exists or item['value'] is None and item['datatype'] in ('matrix','fltMatrix')
                     else vector(item['value'], count))
            inputs.append(RetiredBodyInput(source, destination, item['destination_uuid'],
                                           item['datatype'], value, origin,exists))
        result.append(CharacterRetiredBodyJoint(address, identity, parent,
            vector(row['matrix'], 16), order, index, tuple(inputs),original_inputs,
            tuple(removed),tuple(records),tuple(tuple(item) for item in properties)))
    paths = {row.path for row in result}
    if (len(paths) != len(result) or len({row.uuid for row in result}) != len(result)
            or len({row.body_index for row in result}) != len(result)
            or removed_ids & {row.uuid for row in result}):
        raise CharacterRegistryError('末端清理身份重复')
    if any(row.parent not in live_nodes | paths for row in result):
        raise CharacterRegistryError('已清理末端的父链未登记')
    if any(joint.path.startswith(retired + '|') for retired in paths for joint in body):
        raise CharacterRegistryError('被清理关节仍有存活的 Body 子关节')
    return tuple(result)


def frozen_origin(row, item):
    """Version 8 origins remain recoverable from the captured deleted graph."""
    if item.source_uuid:
        return item.source_uuid
    source = item.source.split('.', 1)[0]
    if source == row.path:
        return row.uuid
    matches = tuple(node.uuid for node in row.removed_nodes if node.path == source)
    if len(matches) != 1:
        from .character_registry import CharacterRegistryError
        raise CharacterRegistryError('末端缓存值缺少唯一删除来源身份')
    return matches[0]


def forget_deleted_retirement_inputs(registration, deleted_ids):
    """Native dagPose cleanup can remove a cached destination itself.

    The adapter supplies observed, deleted UUIDs from its native operation.
    Keep the original Body and solver correspondence, dropping only inputs
    whose actual destination has ceased to exist.
    """
    from dataclasses import replace
    from .character_registry import CharacterRegistryError,encode_registration
    identities = frozenset(deleted_ids)
    if any(not isinstance(value,str) or not value for value in identities):
        raise CharacterRegistryError('原版清理的已删除目标身份无效')
    if identities & {node.uuid for node in registration.nodes}:
        raise CharacterRegistryError('缓存目标清理不能隐式删除登记的存活节点')
    updated = replace(registration,retired_body=tuple(replace(row,
        frozen_inputs=tuple(item for item in row.frozen_inputs
                            if item.destination_uuid not in identities))
        for row in registration.retired_body))
    encode_registration(updated)
    return updated


def complete_body_bindings(registration):
    """Original correspondence remains complete after optional export cleanup."""
    from .character_registry import CharacterBindJoint
    result = list(registration.body)
    for row in sorted(getattr(registration, 'retired_body', ()), key=lambda item:item.body_index):
        result.insert(row.body_index, CharacterBindJoint(row.path, row.parent, row.matrix))
    return tuple(result)


def retire_body_correspondence(registration, retired, live_nodes, live_channels):
    """Apply a captured native deletion without removing FK/IK records."""
    from dataclasses import replace
    from .character_registry import encode_registration, CharacterRegistryError
    previous = {row.path: row for row in registration.retired_body}
    body_by_path = {row.path: row for row in registration.body}
    node_by_path = {row.path: row for row in registration.nodes}
    indices = {row.path:index for index,row in enumerate(complete_body_bindings(registration))}
    for row in retired:
        bind = body_by_path.get(row.path)
        node = node_by_path.get(row.path)
        if (bind is None or node is None or node.node_type != 'joint'
                or row.uuid != node.uuid or row.matrix != bind.matrix
                or row.parent != bind.parent or row.path in previous
                or row.body_index != indices[row.path]):
            raise CharacterRegistryError('末端清理记录不对应原登记 Body 身份')
        previous[row.path] = row
    retired_paths = frozenset(previous)
    updated = replace(registration,
        body=tuple(joint for joint in registration.body if joint.path not in retired_paths),
        nodes=tuple(live_nodes), channels=tuple(live_channels),
        retired_body=tuple(previous.values()))
    # Closed schema checks the complete spline and RP correspondence using
    # the retired bind records, while only live nodes become scene members.
    encode_registration(updated)
    return updated
