"""Replay the original scaling graph, independent of later hierarchy edits."""
from adv_py.core.body_game_scaling import (
    game_scaling_result_states, audit_body_game_scaling, audit_body_game_scaling_nodes,
)
from adv_py.core.original_game_scaling_record import (
    decode, remap_record, replace_joint_uuids, frozen_inputs, live_node_plan,
)
from adv_py.core.character_registry import CharacterRegistryError
from .maya_game_scaling_state import MARKER
from .maya_game_registration import source_registration, refresh_hierarchy, scene_ids, remember_generated_nodes


def restore(host, text):
    host._require_transaction()
    c = host._game_scaling_cmds()
    before, original = decode(text)
    retired = set(original.retired_joints)
    retired_ids = {row.path: row.uuid for row in before if row.path in retired}

    def address(node):
        if node in retired:
            # A newly created UnrealRoot may share the deleted joint's old name.
            # Keep that old identity retired, without adopting the new object.
            suffix = (retired_ids[node] or 'missing').replace('-', '_')
            return host.scene_address('|Group|DeformationSystem|__retired_' + suffix)
        leaf = node.rsplit('|', 1)[-1]
        physical = host.scene_address(leaf)
        paths = c.ls(physical, long=True) or []
        if len(paths) > 1:
            raise CharacterRegistryError('Game Scaling 重建角色不唯一：' + leaf)
        if paths:
            return paths[0]
        if leaf.rsplit(':', 1)[-1].startswith('GameEngineScalingSSCMPD'):
            return physical
        # A recorded virtual ancestor may be a deleted node, but every live
        # driver and destination is checked before its connection is written.
        return host.scene_address(node)

    updated = remap_record(text, address)
    before, plan = decode(updated)
    inputs = frozen_inputs(updated)
    replay = live_node_plan(plan, inputs)
    current = host.capture_game_scaling_joints()
    identities = {row.path: row.uuid for row in current}
    updated = replace_joint_uuids(updated, identities)
    before, plan = decode(updated)
    desired = game_scaling_result_states(before, plan)
    expected = {row.path for row in desired}
    if not expected <= set(identities):
        raise CharacterRegistryError('Game Scaling 重建缺少源关节')
    registration = source_registration(host)
    nodes_before = scene_ids(host)
    host._transaction_changed = True
    pattern = (host.namespace + ':' if host.namespace else '') + 'GameEngineScalingSSCMPD*'
    old_nodes = c.ls(pattern, type='multiplyDivide') or []
    if old_nodes:
        c.delete(old_nodes)
    # First create the stored channels and retain their original inputs. They
    # are also the source of FK frame scale, including native Disable state.
    for row in desired:
        marker = row.path + '.GameEngineScalingSSC'
        if row.has_marker and not c.objExists(marker):
            c.addAttr(row.path, longName='GameEngineScalingSSC', attributeType='bool', defaultValue=True)
        c.setAttr(row.path + '.segmentScaleCompensate', row.segment_scale_compensate)
        for axis, present, source, value in zip('XYZ', row.stored_attributes, row.stored_sources, row.stored_values):
            plug = row.path + '.GameEngineScalingS' + axis
            if present and not c.objExists(plug):
                c.addAttr(row.path, longName='GameEngineScalingS' + axis, attributeType='double')
            if present:
                _edge(c, plug, source)
                if source is None:
                    c.setAttr(plug, value)
    # All source-native compensation nodes exist before wiring their inputs.
    for spec in replay.nodes:
        local = host._cmds.identity.to_local(spec.name) if hasattr(host._cmds, 'identity') else spec.name
        actual = host._cmds.createNode('multiplyDivide', name=local, skipSelect=True)
        c.setAttr(host.scene_address(actual) + '.operation', spec.operation)
        if spec.input1_constant is not None:
            c.setAttr(spec.name + '.input1', *spec.input1_constant, type='double3')
    for spec in replay.nodes:
        for axis, source in zip('XYZ', spec.input1_sources):
            if source:
                _edge(c, spec.name + '.input1' + axis, source)
        for axis, source in zip('XYZ', spec.input2_sources):
            if source:
                _edge(c, spec.name + '.input2' + axis, source)
    for target, value in inputs:
        _edge(c, target, None)
        c.setAttr(target, value)
    for row in desired:
        joint = next(item for item in plan.joints if item.path == row.path)
        reset = tuple(axis.axis for axis in joint.axes if plan.enable and axis.disconnect_scale_source)
        _scale(c, row.path, row.scale_sources, None, reset=reset)
        if row.fk_parent_constraint is not None:
            _scale(c, row.fk_parent_constraint, row.fk_parent_scale_sources,
                   row.fk_parent_compound_scale_source)
        for target, sources, compound in zip(row.fk_parent_extra_constraints,
                row.fk_parent_extra_scale_sources, row.fk_parent_extra_compound_sources):
            _scale(c, target, sources, compound)
    plug = host.scene_address('DeformationSystem.' + MARKER)
    if not c.objExists(plug):
        c.addAttr(host.scene_address('DeformationSystem'), longName=MARKER, dataType='string')
    c.setAttr(plug, lock=False)
    # Normalize physical addresses back to this replacement character's local
    # namespace. The original calculation basis is still retained separately.
    if hasattr(host._cmds, 'identity'):
        updated = remap_record(updated, host._cmds.identity.to_local)
    c.setAttr(plug, updated, type='string', lock=True)
    actual = tuple(row for row in host.capture_game_scaling_joints() if row.path in expected)
    issues = audit_body_game_scaling(plan, before, actual)
    issues += audit_body_game_scaling_nodes(replay, host.capture_game_scaling_nodes(), frozen_inputs=inputs)
    if issues:
        raise CharacterRegistryError('；'.join(issues))
    refresh_hierarchy(host, registration)
    remember_generated_nodes(host, nodes_before)
    c.select(clear=True)


def _edge(c, target, source):
    previous = c.connectionInfo(target, sourceFromDestination=True) or None
    if source and not c.objExists(source):
        raise CharacterRegistryError('Game Scaling 重建输入缺失：' + source)
    if previous and (source is None or not c.isConnected(source, target)):
        c.disconnectAttr(previous, target)
    if source and not c.isConnected(source, target):
        c.connectAttr(source, target)


def _scale(c, target, sources, compound, *, reset=()):
    plug = target + '.scale'
    previous = c.connectionInfo(plug, sourceFromDestination=True) or None
    if compound is None and all(
            c.isConnected(source, plug + axis) if source else not c.connectionInfo(plug + axis, sourceFromDestination=True)
            for axis, source in zip('XYZ', sources)):
        for axis in reset:
            if sources['XYZ'.index(axis)] is None:
                c.setAttr(plug + axis, 1)
        return
    if previous and (compound is None or not c.isConnected(compound, plug)):
        c.disconnectAttr(previous, plug)
    if compound:
        _edge(c, plug, compound)
        return
    for axis, source in zip('XYZ', sources):
        _edge(c, plug + axis, source)
        if source is None and axis in reset:
            c.setAttr(plug + axis, 1)
