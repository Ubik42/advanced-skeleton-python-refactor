"""Keep original Game Engine graph edits readable by the existing registry.

This does not change the native rig calculation. It refreshes the same scene
objects and source records after an explicitly requested hierarchy operation.
"""
from dataclasses import replace

from adv_py.core.character_registry import (
    REGISTRY_NAME, CharacterRegistryError, encode_registration,
)
from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
from .maya_original_control_identity import registration
from .maya_original_control_orient import _by_uuid, _parent
from .maya_driving_registration import _rebase_records, _write_string


def refresh_hierarchy(host, before, *, removed_ids=frozenset(), added_paths=()):
    if before is None:
        return None
    host._require_transaction()
    c = host._cmds
    membership_ids = tuple(node.uuid for node in before.nodes)
    rewrites = []
    retained = []
    for node in before.nodes:
        try:
            current = _by_uuid(host, node.uuid)
        except ValueError:
            if node.uuid in removed_ids:
                continue
            raise
        if c.nodeType(current) != node.node_type:
            raise CharacterRegistryError('Game Engine 操作改变了原节点类型')
        if current != node.path:
            rewrites.append((node.path, current))
        retained.append(node)
    removed_paths = {node.path for node in before.nodes if node.uuid in removed_ids}
    if any(joint.path in removed_paths for joint in before.body):
        raise CharacterRegistryError('Game Engine 操作删除了原 Body 关节')
    from .maya_game_scaling_state import remember_removed_joints
    remember_removed_joints(host, removed_paths)
    before = replace(before, nodes=tuple(retained), channels=tuple(
        channel for channel in before.channels if channel.node not in removed_paths))
    mapping = FitPartFinalPaths((), (), tuple(rewrites))
    changed = rebase_plan_paths_after_parts(before, mapping)
    _rebase_records(host, before, mapping, (), None)
    # Reparenting an individual Part changes its actual direct parent, which
    # cannot be derived by substituting its old parent's path.
    body = tuple(replace(joint, parent=_parent(c, joint.path)) for joint in changed.body)
    channels = {channel.node + '.' + channel.attribute for channel in changed.channels}
    paths = tuple(dict.fromkeys((*[row.path for row in changed.nodes], *added_paths)))
    nodes = tuple(replace(node, inputs=tuple(
        (attribute, source) for attribute, source in node.inputs
        if not (node.path + '.' + attribute in channels
                and host._character_direct_animation(source))))
        for node in (host.capture_character_registration_node(path) for path in paths))
    changed = replace(changed, nodes=nodes, body=body)
    host._validate_character_registration(changed)
    if tuple(row.uuid for row in nodes) != membership_ids:
        _write_members(host, nodes)
    _write_string(c, REGISTRY_NAME + '.advPyRegistryDocument', encode_registration(changed))
    return changed


def _write_members(host, nodes):
    """Replace native message membership only when the owned set changed."""
    c = host._cmds
    plug = REGISTRY_NAME + '.members'
    c.setAttr(plug, lock=False)
    for index in c.getAttr(plug, multiIndices=True) or []:
        target = plug + '[' + str(index) + ']'
        c.setAttr(target, lock=False)
        source = c.connectionInfo(target, sourceFromDestination=True)
        if source:
            c.disconnectAttr(source, target)
    for index, node in enumerate(nodes):
        c.connectAttr(node.path + '.message', plug + '[' + str(index) + ']')
    c.setAttr(plug, lock=True)


def source_registration(host):
    return registration(host)


def remember_generated_nodes(host, before_ids):
    """Append only this operation's actual native node difference to AllSet."""
    c = host._cmds
    if not c.objExists('AllSet'):
        return ()
    added = []
    for node in c.ls(long=True) or []:
        ids = c.ls(node, uuid=True) or []
        if len(ids) != 1:
            raise CharacterRegistryError('Game Engine 新节点身份不唯一')
        if ids[0] not in before_ids:
            added.append(node)
    if added:
        c.sets(added, add='AllSet')
    return tuple(added)


def scene_ids(host):
    c = host._cmds
    return frozenset(identity for node in c.ls(long=True) or []
                     for identity in c.ls(node, uuid=True) or [])
