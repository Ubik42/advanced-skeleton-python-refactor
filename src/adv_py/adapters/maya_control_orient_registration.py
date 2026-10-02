"""Refresh native controller-frame edits by the same Maya object identities."""
from dataclasses import replace

from adv_py.core.character_registry import (
    CharacterRegistryError, REGISTRY_NAME, canonical, encode_registration,
    exact, path, safe_json,
)
from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
from .maya_original_control_orient import MARKER, FRAME_KEYS, _by_uuid, _path, _parent
from .maya_driving_registration import _rebase_records, _write_string


def detached_sdk_child(host, sdk, child):
    """Recognize only a recorded native Detach member's temporary parent."""
    from .maya_original_control_orient_detach import _session
    from .maya_original_control_orient import DETACH_HOLDER, _uuid
    c = host._cmds
    if not c.objExists(DETACH_HOLDER):
        return False
    sdk_id, child_id = _uuid(c, sdk), _uuid(c, child)
    for row in _session(c):
        if row['previous'] != sdk_id or row['member'] != child_id:
            continue
        holder = _by_uuid(host, row['holder'])
        return (_parent(c, child) == holder
                and _parent(c, holder) == _path(c, DETACH_HOLDER))
    return False


def _refresh_sdk_children(host, nodes):
    from .maya_driving_registration import SDK_MARKER
    from .maya_original_control_orient import DETACH_HOLDER, _uuid
    c = host._cmds
    session = ()
    if c.objExists(DETACH_HOLDER):
        from .maya_original_control_orient_detach import _session
        session = _session(c)
    for node in nodes:
        plug = node.path + '.' + SDK_MARKER
        if not c.objExists(plug):
            continue
        record = exact(safe_json(c.getAttr(plug)), ('child', 'scale'))
        child = record['child']
        candidate = child if c.objExists(child) else None
        if candidate is not None:
            # Source Set Axis inserts CustomOrient between an already existing
            # SDK and its Extra. Follow that same object upward to its direct
            # carrying layer; do not replace its scale driver or curve inputs.
            while candidate and _parent(c, candidate) != node.path:
                candidate = _parent(c, candidate)
        if candidate is None:
            member = next((row['member'] for row in session
                           if row['previous'] == _uuid(c, node.path)), None)
            if member is not None:
                candidate = _by_uuid(host, member)
        if candidate is None:
            raise CharacterRegistryError('朝向编辑后 SDK 的原承载层失效：' + node.path)
        if candidate != child:
            _write_string(c, plug, canonical(dict(child=candidate, scale=record['scale'])))


def _matrix_plug(host, plug):
    node, attribute = plug.split('.', 1)
    node = host._resolve_connected_node(node)
    if attribute in ('parentInverseMatrix', 'worldInverseMatrix'):
        attribute += '[0]'
    return node + '.' + attribute


def _replace_edges(value, replacements, *, normalize=lambda plug: plug):
    """Rewrite the exact recorded input edges replaced by native Inbetween.

    Other values and strings are preserved. A restore-command string belongs
    to Extra, while the source graph records continue describing real inputs.
    """
    if isinstance(value, list):
        return [_replace_edges(item, replacements, normalize=normalize) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in ('connections', 'outputs') and isinstance(item, list):
            rows = []
            for row in item:
                if not isinstance(row, list) or len(row) != 2:
                    rows.append(row)
                    continue
                source, destination = row
                full_destination = (value['name'] + '.' + destination
                    if key == 'connections' and 'name' in value else destination)
                updated = replacements.get((normalize(source), normalize(full_destination)), source)
                rows.append([updated, destination])
            result[key] = rows
        else:
            result[key] = _replace_edges(item, replacements, normalize=normalize)
    return result


def refresh(host, before, *, edges=(), added=(), removed=()):
    """Keep channel roles and bind data; update only real reparented objects.

    The existing registry extension API appends members. CustomOrient's
    remove/recreate operation can also remove members, so this operation
    writes the complete message array after the full graph has passed audit.
    """
    host._require_transaction()
    c = host._cmds
    rewrites = []
    alive = []
    removed = set(removed)
    for node in before.nodes:
        try:
            current = _by_uuid(host, node.uuid)
        except ValueError:
            if node.uuid not in removed:
                raise CharacterRegistryError('朝向编辑删除了原角色节点：' + node.path)
            continue
        if c.nodeType(current) != node.node_type:
            raise CharacterRegistryError('朝向编辑改变了原节点类型：' + node.path)
        alive.append(node)
        if current != node.path:
            rewrites.append((node.path, current))
    mapping = FitPartFinalPaths((), (), tuple(rewrites))
    changed = rebase_plan_paths_after_parts(replace(before, nodes=tuple(alive)), mapping)
    _rebase_records(host, replace(before, nodes=tuple(alive)), mapping, (), None)
    _refresh_sdk_children(host, changed.nodes)
    if edges:
        from .maya_source_graph_records import RECORDS
        replacement = {}
        for source, destination, new_source in edges:
            source = mapping.remap_body_reference(source)
            destination = mapping.remap_body_reference(destination)
            new_source = mapping.remap_body_reference(new_source)
            replacement[(_matrix_plug(host, source), _matrix_plug(host, destination))] = _matrix_plug(host, new_source)
        owners = [node.path for node in changed.nodes]
        owners.extend(c.sets('AllSet', query=True) or [] if c.objExists('AllSet') else [])
        for owner in dict.fromkeys(owners):
            for attribute in RECORDS:
                plug = owner + '.' + attribute
                if not c.objExists(plug):
                    continue
                value = safe_json(c.getAttr(plug))
                updated = _replace_edges(value, replacement,
                    normalize=lambda plug: _matrix_plug(host, plug))
                if updated != value:
                    _write_string(c, plug, canonical(updated))
    new = list(added)
    for custom in c.ls('CustomOrient*', type='transform', long=True) or []:
        if not c.objExists(custom + '.' + MARKER):
            continue
        record = exact(safe_json(c.getAttr(custom + '.' + MARKER)), FRAME_KEYS)
        updated = dict(record, control=_by_uuid(host, record['control_uuid']),
                       reverse=_by_uuid(host, record['reverse_uuid']))
        if updated != record:
            _write_string(c, custom + '.' + MARKER, canonical(updated))
        record = updated
        new.extend((custom, record['reverse']))
    nodes = []
    known = set()
    channel_plugs = {channel.node + '.' + channel.attribute for channel in changed.channels}
    for current_path in (*[node.path for node in changed.nodes], *new):
        current_path = _path(c, current_path)
        if current_path in known:
            continue
        node = host.capture_character_registration_node(current_path)
        nodes.append(replace(node, inputs=tuple((attribute, source)
            for attribute, source in node.inputs
            if not (current_path + '.' + attribute in channel_plugs
                    and host._character_direct_animation(source)))))
        known.add(current_path)
    changed = replace(changed, nodes=tuple(nodes))
    if changed.compatibility_digest != before.compatibility_digest:
        raise CharacterRegistryError('朝向插层改变了角色绑定或动画通道语义')
    host._validate_character_registration(changed)
    host._transaction_changed = True
    document = REGISTRY_NAME + '.advPyRegistryDocument'
    _write_string(c, document, encode_registration(changed))
    raw = getattr(c, 'raw', c)
    members = host.scene_address(REGISTRY_NAME + '.members')
    raw.setAttr(members, lock=False)
    try:
        for index in raw.getAttr(members, multiIndices=True) or []:
            raw.removeMultiInstance(members + '[' + str(index) + ']', breakConnections=True)
        for index, node in enumerate(changed.nodes):
            c.connectAttr(node.path + '.message', REGISTRY_NAME + '.members[' + str(index) + ']')
    finally:
        raw.setAttr(members, lock=True)
    return changed, mapping


def audit(host, registration):
    c = host._cmds
    members = {node.path for node in registration.nodes}
    for node in registration.nodes:
        plug = node.path + '.' + MARKER
        if not c.objExists(plug):
            continue
        if node.node_type != 'transform' or not c.getAttr(plug, lock=True):
            raise CharacterRegistryError('原版 CustomOrient 层类型或登记锁定状态变化')
        record = exact(safe_json(c.getAttr(plug)), FRAME_KEYS)
        control, reverse = path(record['control']), path(record['reverse'])
        if control not in members or reverse not in members:
            raise CharacterRegistryError('原版 CustomOrient 的控制器或补偿层未登记')
        if (_by_uuid(host, record['control_uuid']) != control
                or _by_uuid(host, record['reverse_uuid']) != reverse):
            raise CharacterRegistryError('原版 CustomOrient 的原控制器或补偿层身份改变')
        if not control.startswith(node.path + '|'):
            raise CharacterRegistryError('原版 CustomOrient 不再承载原控制器')
        parent = _parent(c, reverse)
        if parent != control and (not parent or _parent(c, parent) != control
                                  or 'Sub' not in parent.rsplit('|', 1)[-1]):
            raise CharacterRegistryError('原版 CustomOrientReverse 的父级改变')
