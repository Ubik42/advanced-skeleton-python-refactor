"""Audit ADV's retained scale-driver detour without rewriting source records."""
from contextlib import contextmanager

from adv_py.core.character_registry import canonical, CharacterRegistryError
from adv_py.core.original_game_scaling_record import (
    decode, encode, map_addresses, mark_retired, frozen_inputs,
    freeze_retired_inputs, live_node_plan,
)
from adv_py.core.body_game_scaling import audit_body_game_scaling, audit_body_game_scaling_nodes

MARKER = 'advPySourceGameScaling'


def _scene_address(host, address):
    """Resolve the active Spline role, then the containing character."""
    from .maya_spline_scope import SplineCommands
    from adv_py.core.spline_names import remap_spline_value
    commands = host._cmds
    while isinstance(commands, SplineCommands):
        address = remap_spline_value(address, commands.system)
        commands = commands.commands
    return host.scene_address(address)


def save(host, before, plan):
    c = host._cmds
    if hasattr(c, 'identity'):
        before, plan = map_addresses(before, plan, c.identity.to_local)
    plug = 'DeformationSystem.' + MARKER
    if not c.objExists(plug):
        c.addAttr('DeformationSystem', longName=MARKER, dataType='string')
    c.setAttr(plug, lock=False)
    c.setAttr(plug, encode(before, plan), type='string', lock=True)


def load(host):
    text = retained_record(host)
    if text is None:
        return None
    before, plan = decode(text)
    before, plan = map_addresses(before, plan, host.scene_address)
    raw = host._game_scaling_cmds()
    for row in before:
        if row.path not in plan.retired_joints:
            continue
        if (raw.ls(row.uuid, long=True) if row.uuid else raw.objExists(row.path)):
            raise CharacterRegistryError('Game Engine Scaling 已删除导出关节身份仍存在')
    expected = {row.path for row in plan.joints} - set(plan.retired_joints)
    current = tuple(row for row in host.capture_game_scaling_joints() if row.path in expected)
    issues = audit_body_game_scaling(plan, before, current)
    inputs = tuple((host.scene_address(target), value) for target, value in frozen_inputs(text))
    issues += audit_body_game_scaling_nodes(live_node_plan(plan, inputs),
        host.capture_game_scaling_nodes(), frozen_inputs=inputs)
    if issues:
        raise CharacterRegistryError('；'.join(issues))
    return before, plan


def retained_record(host):
    """Read an old record using the surviving scene as its cache evidence.

    Older v2 documents have no historical cached-input baseline. Read the
    actual disconnected inputs once into the returned v3 snapshot; callers
    can carry it into rebuild without changing the live scene during a read.
    Already recorded values remain fixed and are audited by load().
    """
    c = host._cmds
    plug = 'DeformationSystem.' + MARKER
    if not c.objExists(plug):
        return None
    if c.getAttr(plug, type=True) != 'string' or not c.getAttr(plug, lock=True):
        raise CharacterRegistryError('Game Engine Scaling 原版图登记状态变化')
    return _freeze_deleted_inputs(host, c.getAttr(plug))


def _freeze_deleted_inputs(host, text):
    before, plan = decode(text)
    retired = set(plan.retired_joints)
    if not retired:
        return text
    c = host._game_scaling_cmds()
    known = dict(frozen_inputs(text))
    pending = []
    for node in plan.nodes:
        for kind in ('input1', 'input2'):
            for axis, source in zip('XYZ', getattr(node, kind + '_sources')):
                if not source or source.partition('.')[0] not in retired:
                    continue
                target = node.name + '.' + kind + axis
                if target in known:
                    continue
                physical = host.scene_address(target)
                if not c.objExists(physical) or c.connectionInfo(physical, sourceFromDestination=True):
                    raise CharacterRegistryError('Game Scaling 删除关节后的原输入未保留：' + target)
                pending.append((target, float(c.getAttr(physical))))
    return freeze_retired_inputs(text, pending) if pending else text


def remember_removed_joints(host, paths):
    """Keep the source's orphan MPD nodes after native export-joint deletion."""
    c = host._cmds
    plug = 'DeformationSystem.' + MARKER
    if not paths or not c.objExists(plug):
        return
    local = tuple(c.identity.to_local(path) if hasattr(c, 'identity') else path for path in paths)
    updated = _freeze_deleted_inputs(host, mark_retired(c.getAttr(plug), local))
    c.setAttr(plug, lock=False)
    try:
        c.setAttr(plug, updated, type='string')
    finally:
        c.setAttr(plug, lock=True)


@contextmanager
def validation(host):
    previous = getattr(host, '_original_game_scaling_validation', None)
    host._original_game_scaling_validation = load(host)
    try:
        yield
    finally:
        host._original_game_scaling_validation = previous


def original_scale_connection(host, source, destination):
    c = host._cmds
    if not c.objExists(source) or not c.objExists(destination):
        from .maya_character_body_retirement import is_connected_or_retired
        return is_connected_or_retired(host,source,destination)
    if c.isConnected(source, destination):
        return True
    context = getattr(host, '_original_game_scaling_validation', None)
    if context is None:
        # A source-scale stage audit may run outside registration validation.
        context = load(host)
    if context is None:
        return False
    before, plan = context
    target_node, target_attr = destination.split('.', 1)
    source_node, source_attr = source.split('.', 1)
    target_physical = _scene_address(host, target_node)
    source_physical = _scene_address(host, source_node)
    if target_attr in ('scale', 's'):
        children = c.attributeQuery(source_attr, node=source_node, listChildren=True) or []
        return len(children) == 3 and all(original_scale_connection(host,
            source_node + '.' + child, target_node + '.scale' + axis)
            for child, axis in zip(children, 'XYZ'))
    axis = target_attr[-1] if target_attr in tuple('scale' + axis for axis in 'XYZ') else None
    if axis is None:
        return False
    for prior, row in zip(before, plan.joints):
        slot = 'XYZ'.index(axis)
        if row.path in plan.retired_joints:
            continue
        if row.path == target_physical and plan.enable and row.marker_required:
            stored = target_node + '.GameEngineScalingS' + axis
            original = prior.stored_sources[slot] if prior.stored_attributes[slot] else prior.scale_sources[slot]
            if (original and _scene_address(host, source) == original
                    and c.isConnected(source, stored)):
                # The native write has been fully audited by load(): ordinary
                # joints use MPD output; Parts retain source's scale=1 branch.
                return True
        if row.path == source_physical and source_attr == 'scale' + axis:
            # Source deliberately keeps FKParentConstraintTo fed from the
            # stored attribute even after switching back to Maya scaling.
            targets = (prior.fk_parent_constraint, *prior.fk_parent_extra_constraints)
            if (target_physical in targets
                    and c.isConnected(source_node + '.GameEngineScalingS' + axis, destination)):
                return True
    return False


def original_scale_source(host, joint, axis):
    """Read the retained pre-detour input when capturing the rebuild policy."""
    c = host._cmds
    context = getattr(host, '_original_game_scaling_validation', None)
    if context is None:
        context = load(host)
    if context is not None:
        before, plan = context
        physical = _scene_address(host, joint)
        for prior, row in zip(before, plan.joints):
            if (row.path != physical or row.path in plan.retired_joints
                    or not plan.enable or not row.marker_required):
                continue
            index = 'XYZ'.index(axis)
            source = prior.stored_sources[index] if prior.stored_attributes[index] else prior.scale_sources[index]
            return c.identity.to_local(source) if source and hasattr(c, 'identity') else source or ''
    return c.connectionInfo(joint + '.scale' + axis, sourceFromDestination=True) or ''


def original_compound_scale_source(host, joint):
    c = host._cmds
    context = getattr(host, '_original_game_scaling_validation', None)
    if context is None:
        context = load(host)
    physical = _scene_address(host, joint)
    detour = (context is not None and context[1].enable and any(
        row.path == physical and row.path not in context[1].retired_joints
        and row.marker_required for row in context[1].joints))
    if not detour:
        direct = c.connectionInfo(joint + '.scale', sourceFromDestination=True)
        if direct:
            return direct
    sources = tuple(original_scale_source(host, joint, axis) for axis in 'XYZ')
    if not all(sources):
        return ''
    nodes = {source.split('.', 1)[0] for source in sources}
    if len(nodes) != 1:
        return ''
    node = nodes.pop()
    parents = tuple(c.attributeQuery(source.split('.', 1)[1], node=node, listParent=True) or []
                    for source in sources)
    if not all(len(parent) == 1 for parent in parents) or len({parent[0] for parent in parents}) != 1:
        return ''
    return node + '.' + parents[0][0]


def original_segment_scale_compensate(host, joint):
    """Read the authored SSC flag before the optional native Game switch."""
    if not host._cmds.objExists(joint):
        from .maya_character_body_retirement import source_property
        return source_property(host,joint,'segmentScaleCompensate')
    context = getattr(host, '_original_game_scaling_validation', None)
    if context is None:
        context = load(host)
    if context is not None:
        before, plan = context
        physical = _scene_address(host, joint)
        for prior, row in zip(before, plan.joints):
            if row.path == physical and row.path not in plan.retired_joints and row.marker_required:
                return (prior.authored_segment_scale_compensate
                    if prior.authored_segment_scale_compensate is not None
                    else prior.segment_scale_compensate)
    return bool(host._cmds.getAttr(joint + '.segmentScaleCompensate'))


def original_scale_is_ik(host, joint, source, saved):
    if source is None:
        return None
    c = host._cmds
    node = source.split('.', 1)[0]
    bare = node.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
    if bare.startswith('ScaleBlend'):
        return True
    if saved is not None:
        for limb in saved.source_limbs:
            for binding in limb.joints:
                if host.scene_address(binding.body) != joint:
                    continue
                name, side = binding.body.rsplit('|', 1)[-1].rsplit('_', 1)
                if node == host.scene_address('AdvPy_' + name + 'IKFKBlend_' + side + 'Scale'):
                    return True
    # Spline/Part source records identify their exact ScaleBlend node even
    # where Python's implementation name differs from the original role.
    local_joint = c.identity.to_local(joint) if hasattr(c, 'identity') else joint
    from adv_py.core.source_body_matrix import decode_source_body_matrix
    for marker in ('advPySourceLocalScale', 'advPySourceBendyMatrix'):
        plug = local_joint + '.' + marker
        if not c.objExists(plug):
            continue
        record = decode_source_body_matrix(c.getAttr(plug))
        if any(row.kind == 'blendColors' and host.scene_address(row.name) == node for row in record.nodes):
            return True
    return False
