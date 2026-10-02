"""Keep Python scene addresses valid after the source SDK parent insertion.

Maya reparents the original nodes by identity. Its native connections and
sets follow that change, whereas the Python's saved DAG strings do not.
This updates only those addresses; bind matrices and channel roles stay put.
"""
from dataclasses import replace
import re

from adv_py.core.character_registry import (
    CharacterRegistryError, canonical, safe_json, exact, path,
)
from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts

SDK_MARKER = 'advPySourceDrivingSDK'


def _plug(host, plug):
    node, attribute = plug.split('.', 1)
    aliases = {'s': 'scale', 'sx': 'scaleX', 'sy': 'scaleY', 'sz': 'scaleZ'}
    return host._resolve_connected_node(node) + '.' + aliases.get(attribute, attribute)


def _scale_record(host, sdk, edges):
    if not edges:
        return (), None
    c = host._cmds
    name = sdk + 'ScaleMPD'
    replacements = tuple((_plug(host, source), _plug(host, target),
                          _plug(host, output)) for source, target, output in edges)
    inputs = []
    for compound in ('input1', 'input2'):
        plug = name + '.' + compound
        source = c.connectionInfo(plug, sourceFromDestination=True)
        if source:
            inputs.append((_plug(host, source), compound))
        else:
            for axis in 'XYZ':
                source = c.connectionInfo(plug + axis, sourceFromDestination=True)
                if not source:
                    raise CharacterRegistryError('SDK 缩放乘积输入缺失')
                inputs.append((_plug(host, source), compound + axis))
    return replacements, dict(name=name, kind='multiplyDivide',
                               values=[['operation', 1.]],
                               connections=[list(row) for row in inputs])


def _scale_record_edges(value, replacements, descriptor):
    """Describe only the exact scale edge replaced by source ScaleMPD."""
    changed = False
    if isinstance(value, list):
        result = []
        for item in value:
            updated, touched = _scale_record_edges(item, replacements, descriptor)
            result.append(updated)
            changed |= touched
        return result, changed
    if not isinstance(value, dict):
        return value, False
    result = dict(value)
    for key, item in value.items():
        if key in ('outputs', 'local_scale', 'connections') and isinstance(item, list):
            rows = []
            for row in item:
                if not isinstance(row, list) or len(row) != 2:
                    rows.append(row)
                    continue
                source, target = row
                destination = (value['name'] + '.' + target
                               if key == 'connections' and 'name' in value else target)
                replacement = next((output for previous, end, output in replacements
                                    if (source, destination) == (previous, end)), None)
                rows.append([replacement or source, target])
                changed |= replacement is not None
            result[key] = rows
        else:
            result[key], touched = _scale_record_edges(item, replacements, descriptor)
            changed |= touched
    if changed and 'nodes' in result and isinstance(result['nodes'], list):
        if descriptor['name'] not in {node['name'] for node in result['nodes']}:
            result['nodes'] = [*result['nodes'], descriptor]
    return result, changed


def _write_string(commands, plug, value):
    locked = bool(commands.getAttr(plug, lock=True))
    try:
        if locked:
            commands.setAttr(plug, lock=False)
        commands.setAttr(plug, value, type='string')
    finally:
        if locked:
            commands.setAttr(plug, lock=True)


def _command_addresses(text, rewrites):
    """Readdress saved setAttr text without interpreting or executing it."""
    mapping = FitPartFinalPaths((), (), tuple(rewrites))
    return re.sub(r'\|[A-Za-z_][A-Za-z_0-9:]*'
                  r'(?:\|[A-Za-z_][A-Za-z_0-9:]*)*',
                  lambda match: mapping.remap_body_reference(match.group()), text)


def _rebase_records(host, registration, paths, replacements, descriptor):
    c = host._cmds
    from .maya_source_graph_records import RECORDS
    records = set(RECORDS) | {'advPyPoseData', 'advPyBuildPoseValues',
                             'advPyCustomControlParent', 'advPyIkAlignOwner'}
    physical = tuple((host.scene_address(before), host.scene_address(after))
                     for before, after in paths.body_rewrites)
    both = FitPartFinalPaths((), (), (*paths.body_rewrites, *physical))
    # AllSet also carries graph nodes and buildPose, outside the transform
    # registration. Do not visit another character's namespace or user data.
    owners = [node.path for node in registration.nodes]
    if c.objExists('AllSet'):
        owners.extend(c.sets('AllSet', query=True) or [])
    if c.objExists('buildPose'):
        owners.append('buildPose')
    for old in dict.fromkeys(owners):
        owner = paths.remap_body_reference(old)
        if not c.objExists(owner):
            raise CharacterRegistryError('SDK 插层后记录所属节点缺失：' + owner)
        for attribute in c.listAttr(owner, userDefined=True) or []:
            command = attribute in ('udAttr', 'udExtraAttr', 'advPyBuildPoseCommand',
                                    'CustomOrientRestoreCmd')
            record = attribute in records
            if not (command or record):
                continue
            plug = owner + '.' + attribute
            if c.getAttr(plug, type=True) != 'string':
                continue
            original = c.getAttr(plug) or ''
            if command:
                updated = _command_addresses(original, physical)
            elif original.lstrip().startswith(('{', '[')):
                value = safe_json(original, max_bytes=8_000_000)
                rebased = rebase_plan_paths_after_parts(value, both)
                if descriptor is not None:
                    rebased, _ = _scale_record_edges(rebased, replacements, descriptor)
                updated = canonical(rebased) if rebased != value else original
            else:
                updated = both.remap_body_reference(original)
            if updated != original:
                _write_string(c, plug, updated)


def rebase_after_sdk(host, before, old_child, new_child, sdk, *, scale_edges=()):
    """Refresh the same registered objects, preserving message-array order."""
    if before is None:
        return None  # A source MEL scene has no Python registration to update.
    host._require_transaction()
    paths = FitPartFinalPaths((), (), ((old_child, new_child),))
    changed = rebase_plan_paths_after_parts(before, paths)
    replacements, descriptor = _scale_record(host, sdk, scale_edges)
    _rebase_records(host, before, paths, replacements, descriptor)
    if not any(node.path == old_child or node.path.startswith(old_child + '|')
               for node in before.nodes):
        # A source custom controller may coexist with a registered Body but
        # belong to its own deformation system. Its SDK remains a native
        # source object; do not adopt it into an unrelated Body registration.
        return before
    user_plugs = {channel.node + '.' + channel.attribute for channel in changed.channels}
    nodes = []
    for old in changed.nodes:
        current = host.capture_character_registration_node(old.path)
        if current.uuid != old.uuid or current.node_type != old.node_type:
            raise CharacterRegistryError('SDK 插层替换了角色原节点：' + old.path)
        # Time curves remain user animation rather than structural rig edges.
        nodes.append(replace(current, inputs=tuple(
            (attribute, source) for attribute, source in current.inputs
            if not (current.path + '.' + attribute in user_plugs
                    and host._character_direct_animation(source)))))
    sdk_paths = host._cmds.ls(sdk, long=True) or []
    if len(sdk_paths) != 1:
        raise CharacterRegistryError('SDK 插层节点不唯一')
    if sdk_paths[0] not in {node.path for node in nodes}:
        nodes.append(host.capture_character_registration_node(sdk_paths[0]))
    if new_child not in {node.path for node in nodes}:
        nodes.append(host.capture_character_registration_node(new_child))
    changed = replace(changed, nodes=tuple(nodes))
    if changed.compatibility_digest != before.compatibility_digest:
        raise CharacterRegistryError('SDK 插层改变了原角色的绑定或动画语义')
    c = host._cmds
    c.addAttr(sdk, longName=SDK_MARKER, dataType='string')
    c.setAttr(sdk + '.' + SDK_MARKER, canonical(dict(
        child=new_child, scale=descriptor)), type='string', lock=True)
    host.write_character_registration_extension(before, changed)
    return changed


def refresh_registered_sdks(host):
    """Record completed SDK curve inputs after the full asDsCreate operation."""
    before = host.original_corrective_body_registration()
    if before is None:
        return
    c = host._cmds
    nodes = []
    for node in before.nodes:
        if c.objExists(node.path + '.' + SDK_MARKER):
            node = host.capture_character_registration_node(node.path)
        nodes.append(node)
    # Driving controls added after Body construction are animation controls,
    # too. Their values/curves must join save, pose and rebuild checkpoints.
    # Only the explicit DrivingSystem subtree is adopted; another transform
    # discovered by an upstream BW is not an ownership declaration.
    from adv_py.core.character_registry import CharacterChannel
    channels = list(before.channels)
    known = {(channel.node, channel.attribute) for channel in channels}
    paths = {node.path for node in nodes}
    if c.objExists('DrivingSystem'):
        driving_paths = c.ls('DrivingSystem', long=True) or []
        if len(driving_paths) != 1:
            raise CharacterRegistryError('来源 DrivingSystem 层级不唯一')
        root = driving_paths[0]
        controls = c.listRelatives(root, children=True, type='transform', fullPath=True) or []
        for control in (root, *controls):
            if not c.objExists('AllSet') or not c.sets(control, isMember='AllSet'):
                continue
            if control not in paths:
                nodes.append(host.capture_character_registration_node(control))
                paths.add(control)
            else:
                current = host.capture_character_registration_node(control)
                index = next(index for index, node in enumerate(nodes) if node.path == control)
                if (nodes[index].uuid != current.uuid or nodes[index].node_type != current.node_type):
                    raise CharacterRegistryError('DrivingSystem 控制器原节点身份改变：' + control)
                nodes[index] = replace(current, inputs=tuple(
                    (attribute, source) for attribute, source in current.inputs
                    if not (any(channel.node == control and channel.attribute == attribute
                                for channel in channels)
                            and host._character_direct_animation(source))))
            if control == root:
                continue
            role = control.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
            for attribute in c.listAttr(control, userDefined=True) or []:
                plug = control + '.' + attribute
                if ((control, attribute) in known or c.getAttr(plug, lock=True)
                        or (not c.getAttr(plug, settable=True)
                            and not host._original_driver_time_input(host.scene_address(plug)))
                        or not (c.getAttr(plug, keyable=True) or c.getAttr(plug, channelBox=True))
                        or c.getAttr(plug, type=True) not in
                        ('bool','byte','char','short','long','enum','float','double',
                         'doubleLinear','doubleAngle','time')):
                    continue
                minimum = (float(c.attributeQuery(attribute, node=control, minimum=True)[0])
                           if c.attributeQuery(attribute, node=control, minExists=True) else None)
                maximum = (float(c.attributeQuery(attribute, node=control, maximum=True)[0])
                           if c.attributeQuery(attribute, node=control, maxExists=True) else None)
                channels.append(CharacterChannel('driving.' + role + '.' + attribute,
                                                  control, attribute, minimum, maximum))
                known.add((control, attribute))
    after = replace(before, nodes=tuple(nodes), channels=tuple(channels))
    host.write_character_registration_extension(before, after)


def audit_registered_sdks(host, registration):
    """Audit the inserted source hierarchy and its scale multiplication."""
    c = host._cmds
    owned = {node.path for node in registration.nodes}
    for node in registration.nodes:
        plug = node.path + '.' + SDK_MARKER
        if not c.objExists(plug):
            continue
        if node.node_type != 'transform' or not c.getAttr(plug, lock=True):
            raise CharacterRegistryError('来源 SDK 插层身份无效或记录已解锁')
        record = exact(safe_json(c.getAttr(plug)), ('child', 'scale'))
        child = path(record['child'])
        from .maya_control_orient_registration import detached_sdk_child
        if (child not in owned or ((c.listRelatives(child, parent=True, fullPath=True) or [])
                != [node.path] and not detached_sdk_child(host, node.path, child))):
            raise CharacterRegistryError('来源 SDK 插层不再承载原控制层')
        scale = record['scale']
        if scale is None:
            continue
        exact(scale, ('name', 'kind', 'values', 'connections'))
        name = node.path.rsplit('|', 1)[-1] + 'ScaleMPD'
        if (scale['name'] != name or scale['kind'] != 'multiplyDivide'
                or scale['values'] != [['operation', 1.]]
                or c.nodeType(name) != 'multiplyDivide'
                or c.getAttr(name + '.operation') != 1
                or c.getAttr(name + '.isHistoricallyInteresting') != 0):
            raise CharacterRegistryError('来源 SDK 缩放乘积节点改变')
        expected = scale['connections']
        if (not isinstance(expected, list) or len(expected) not in (2, 6)
                or any(not isinstance(row, list) or len(row) != 2
                       or not all(isinstance(item, str) for item in row) for row in expected)):
            raise CharacterRegistryError('来源 SDK 缩放乘积记录无效')
        attributes = {row[1] for row in expected
                      if isinstance(row, list) and len(row) == 2}
        if attributes not in ({'input1', 'input2'},
                {'input' + str(index) + axis for index in (1, 2) for axis in 'XYZ'}):
            raise CharacterRegistryError('来源 SDK 缩放乘积输入不完整')
        if len(attributes) != len(expected):
            raise CharacterRegistryError('来源 SDK 缩放乘积输入重复')
        for source, attribute in expected:
            if not c.isConnected(source, name + '.' + attribute):
                raise CharacterRegistryError('来源 SDK 缩放乘积接线改变')
