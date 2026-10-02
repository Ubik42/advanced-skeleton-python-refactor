"""Preserve native derived SDK drivers while staging a replacement Body.

Only the graph families authored by ADV's QRotate, OPM-compatible and
custom-blended-attribute procedures are copied. Body solver nodes remain
the new Body's own nodes; time animation transfers through preservation.
"""
from dataclasses import dataclass, replace

from adv_py.core.character_registry import CharacterRegistryError
from .maya_original_control_identity import leaf


def logical_leaf(node):
    # Scoped commands already removed this character's namespace. Preserve
    # any remaining foreign namespace instead of adopting a same-name node.
    return node.rsplit('|', 1)[-1].lstrip(':')


@dataclass(frozen=True)
class DrivingGraphNode:
    properties: object
    values: tuple
    in_all_set: bool


@dataclass(frozen=True)
class DrivingGraphState:
    nodes: tuple[DrivingGraphNode, ...]
    edges: tuple[tuple[str, str], ...]


def _families(control, attribute):
    """Names and types written by MEL 66017, 66093 and 66118."""
    tokens = [token for token in leaf(control).split('_') if token]
    qstem = tokens[0] if tokens else ''
    qside = '_' + tokens[1] if len(tokens) > 1 else ''
    result = {
        qstem + 'QRotateMMTwist' + qside: 'multMatrix',
        qstem + 'QRotateDMTwist' + qside: 'decomposeMatrix',
        **{qstem + 'QRotate' + axis + 'QTETwist' + qside: 'quatToEuler'
           for axis in 'XYZ'},
    }
    stem = leaf(control) + attribute
    result.update({stem + 'MPD': 'multiplyDivide',
                   stem + 'PlusMinusAverage': 'plusMinusAverage',
                   stem + 'SetRange': 'setRange', stem + 'Clamp': 'clamp'})
    if attribute.startswith('opm'):
        source_attribute = attribute[3:]
        result[leaf(control) + 'DM' + source_attribute] = 'decomposeMatrix'
        result[leaf(control) + 'DMMM' + source_attribute] = 'multMatrix'
    result['bw' + leaf(control) + '_' + attribute] = 'blendWeighted'
    return result


def _source(c, plug):
    return c.connectionInfo(plug, sourceFromDestination=True) or ''


def _constants(c, node, kind):
    attributes = {
        'decomposeMatrix': ('inputRotateOrder',),
        'unitConversion': ('conversionFactor',),
        'quatToEuler': ('inputRotateOrder', 'inputQuatX', 'inputQuatY',
                        'inputQuatZ', 'inputQuatW'),
        'multiplyDivide': ('operation', 'input1X', 'input1Y', 'input1Z',
                           'input2X', 'input2Y', 'input2Z'),
        'plusMinusAverage': ('operation',),
        'setRange': tuple(stem + axis for stem in ('value', 'min', 'max', 'oldMin', 'oldMax')
                          for axis in 'XYZ'),
        'clamp': tuple(stem + axis for stem in ('input', 'min', 'max') for axis in 'RGB'),
    }.get(kind, ())
    if kind == 'multMatrix':
        attributes = tuple('matrixIn[' + str(index) + ']'
                           for index in c.getAttr(node + '.matrixIn', multiIndices=True) or [])
    if kind == 'plusMinusAverage':
        attributes += tuple('input1D[' + str(index) + ']'
                            for index in c.getAttr(node + '.input1D', multiIndices=True) or [])
    if kind == 'blendWeighted':
        attributes = tuple(stem + '[' + str(index) + ']'
            for stem in ('input', 'weight')
            for index in c.getAttr(node + '.' + stem, multiIndices=True) or [])
    result = []
    for attribute in attributes:
        plug = node + '.' + attribute
        if not c.objExists(plug) or _source(c, plug):
            continue
        kind = c.getAttr(plug, type=True)
        value = c.getAttr(plug)
        if kind == 'matrix':
            if len(value) == 1 and isinstance(value[0], (tuple, list)):
                value = value[0]
            value = tuple(value)
        result.append((attribute, kind, value))
    return tuple(result)


def capture(host, registration, systems):
    c = host._cmds
    allowed = {}
    plugs = []
    for system in systems:
        for row in system.curves:
            allowed.update(_families(system.control, row.attribute))
            plugs.append(system.control + '.' + row.attribute)
    # A blended driver can consume qRotate/opm channels on the same original
    # controller. Include only its declared UD attributes' native families.
    for system in systems:
        for attribute in c.listAttr(system.control, userDefined=True) or []:
            allowed.update(_families(system.control, attribute))
            if attribute in ('qRotateX', 'qRotateY', 'qRotateZ'):
                plugs.append(system.control + '.' + attribute)
    body_nodes = {logical_leaf(node.path) for node in registration.nodes}
    if c.objExists('AllSet'):
        body_nodes.update(logical_leaf(node) for node in c.sets('AllSet', query=True) or [])
    sdk_curves = {logical_leaf(row.source) for system in systems for row in system.curves}
    from .maya_character_preservation import capture_extension, connections
    pending = list(dict.fromkeys(plugs))
    nodes = {}
    edges = set()
    while pending:
        plug = pending.pop()
        time_input = getattr(host, '_original_driver_time_input', None)
        if time_input is not None and time_input(host.scene_address(plug)):
            continue
        sources = c.listConnections(plug, source=True, destination=False, plugs=True) or []
        for source in sources:
            node = source.split('.', 1)[0]
            name = logical_leaf(node)
            kind = c.nodeType(node)
            if kind.startswith('animCurveT'):
                continue
            if name in sdk_curves:
                continue  # Native curve duplication/restoration follows.
            if name in body_nodes and name not in allowed:
                continue
            if kind == 'unitConversion':
                # This scalar converter is on a discovered source driver
                # input. Its upstream boundary is traversed and checked too.
                allowed[name] = kind
            if name not in allowed or allowed[name] != kind:
                raise CharacterRegistryError('SDK 派生驱动不属于原版已实现网络：' + node)
            if name in nodes:
                continue
            row = capture_extension(host, node)
            if any(c.lockNode(node, query=True, lock=True) or []):
                raise CharacterRegistryError('SDK 派生驱动网络已锁定：' + node)
            nodes[name] = DrivingGraphNode(replace(row, path=name, parent=None, matrix=None,
                connections=()), _constants(c, node, kind),
                bool(c.objExists('AllSet') and c.sets(node, isMember='AllSet')))
            links = connections(host, node)
            edges.update(links)
            pending.extend(destination for upstream, destination in links
                           if destination.split('.', 1)[0] == row.path)
    if not nodes:
        return DrivingGraphState((), ())
    names = set(nodes)
    controls = {logical_leaf(system.control) for system in systems}
    retained = []
    for source, destination in sorted(edges):
        source_node, source_attribute = source.split('.', 1)
        target_node, target_attribute = destination.split('.', 1)
        a, b = logical_leaf(source_node), logical_leaf(target_node)
        if b in names or (a in names and b in controls | body_nodes):
            retained.append((a + '.' + source_attribute, b + '.' + target_attribute))
    return DrivingGraphState(tuple(nodes.values()), tuple(retained))


def restore(host, state):
    host._require_transaction()
    c = host._cmds
    from .maya_character_properties import install
    for node in state.nodes:
        row = node.properties
        if c.objExists(row.path):
            raise CharacterRegistryError('SDK 派生驱动目标节点已存在：' + row.path)
        c.createNode(row.node_type, name=row.path)
        install(host, (row,))
        for attribute, kind, value in node.values:
            if kind == 'matrix':
                c.setAttr(row.path + '.' + attribute, *value, type='matrix')
            else:
                c.setAttr(row.path + '.' + attribute, value)
        if node.in_all_set:
            c.sets(row.path, add='AllSet')
    for source, destination in state.edges:
        if not c.objExists(source) or not c.objExists(destination):
            raise CharacterRegistryError('SDK 派生网络缺少新 Body 接线端点：' + repr((source, destination)))
        previous = _source(c, destination)
        if previous and not c.isConnected(source, destination):
            raise CharacterRegistryError('SDK 派生网络目标已有不同输入：' + destination)
        if not c.isConnected(source, destination):
            c.connectAttr(source, destination)
    for node in state.nodes:
        for name, _, _, locked, _, _ in node.properties.attributes:
            c.setAttr(node.properties.path + '.' + name, lock=locked)
    host._transaction_changed = bool(state.nodes) or host._transaction_changed
