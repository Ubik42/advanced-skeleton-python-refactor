"""Closed native Game Engine Scaling record; never an object loader."""
from dataclasses import asdict, fields, replace
from math import isfinite
from .body_game_scaling import (
    GameScalingJointState, GameScalingAxisPlan, GameScalingJointPlan,
    GameScalingNodeSpec, GameScalingPlan, plan_body_game_scaling,
)
from .character_registry import canonical, exact, safe_json, CharacterRegistryError


STATE_TUPLES = ('scale_sources', 'stored_sources', 'stored_attributes',
                'fk_parent_scale_sources', 'scale_source_ik_roles', 'stored_values')


def _row(value, cls, tuple_fields=(), variable_tuples=()):
    value = dict(exact(value, (field.name for field in fields(cls))))
    for key in tuple_fields:
        if not isinstance(value[key], list) or len(value[key]) != 3:
            raise CharacterRegistryError('Game Engine Scaling 三轴记录无效')
        value[key] = tuple(value[key])
    for key in variable_tuples:
        if not isinstance(value[key], list):
            raise CharacterRegistryError('Game Engine Scaling 跟随列表无效')
        value[key] = tuple(value[key])
    return cls(**value)


def _decode_v1(text):
    raw = exact(safe_json(text), ('version', 'before', 'plan'))
    if type(raw['version']) is not int or raw['version'] != 1:
        raise CharacterRegistryError('Game Engine Scaling 来源版本无效')
    if not isinstance(raw['before'], list) or not 0 < len(raw['before']) <= 10000:
        raise CharacterRegistryError('Game Engine Scaling 关节记录无效')
    states = []
    for row in raw['before']:
        row = dict(exact(row, (field.name for field in fields(GameScalingJointState))))
        extra = row['fk_parent_extra_scale_sources']
        if not isinstance(extra, list) or any(not isinstance(item, list) or len(item) != 3 for item in extra):
            raise CharacterRegistryError('Game Engine Scaling 附加跟随三轴无效')
        row['fk_parent_extra_scale_sources'] = [tuple(item) for item in extra]
        states.append(_row(row, GameScalingJointState, STATE_TUPLES,
            ('fk_parent_extra_constraints', 'fk_parent_extra_scale_sources', 'fk_parent_extra_compound_sources')))
    before = tuple(states)
    data = exact(raw['plan'], ('enable', 'joints', 'nodes', 'remove_old_compensation_nodes', 'retired_joints'))
    if not isinstance(data['joints'], list) or not isinstance(data['nodes'], list):
        raise CharacterRegistryError('Game Engine Scaling 图记录无效')
    joints = []
    for item in data['joints']:
        item = dict(exact(item, (field.name for field in fields(GameScalingJointPlan))))
        if not isinstance(item['axes'], list) or len(item['axes']) != 3:
            raise CharacterRegistryError('Game Engine Scaling 轴记录无效')
        item['axes'] = tuple(_row(axis, GameScalingAxisPlan,
            variable_tuples=('fk_parent_extra_scale_targets',)) for axis in item['axes'])
        extra = item['fk_parent_extra_disconnect_compounds']
        if not isinstance(extra, list) or any(not isinstance(pair, list) or len(pair) != 2 for pair in extra):
            raise CharacterRegistryError('Game Engine Scaling 附加断开接线无效')
        item['fk_parent_extra_disconnect_compounds'] = tuple(tuple(pair) for pair in extra)
        joints.append(GameScalingJointPlan(**item))
    nodes = []
    for item in data['nodes']:
        item = dict(exact(item, (field.name for field in fields(GameScalingNodeSpec))))
        for key in ('input1_sources', 'input2_sources', 'input1_constant'):
            if item[key] is not None:
                if not isinstance(item[key], list) or len(item[key]) != 3:
                    raise CharacterRegistryError('Game Engine Scaling 矩阵节点三轴无效')
                item[key] = tuple(item[key])
        nodes.append(GameScalingNodeSpec(**item))
    retired = data['retired_joints']
    if (not isinstance(retired, list) or any(not isinstance(path, str) for path in retired)
            or len(set(retired)) != len(retired) or not set(retired) <= {row.path for row in before}):
        raise CharacterRegistryError('Game Engine Scaling 已删除关节记录无效')
    plan = GameScalingPlan(data['enable'], tuple(joints), tuple(nodes), data['remove_old_compensation_nodes'], tuple(retired))
    try:
        expected = plan_body_game_scaling(before, enable=plan.enable)
    except (TypeError, ValueError, AttributeError) as exc:
        raise CharacterRegistryError('Game Engine Scaling 原始状态无效') from exc
    if plan != replace(expected, retired_joints=plan.retired_joints):
        raise CharacterRegistryError('Game Engine Scaling 记录不等于原版分支计划')
    return before, plan


def map_addresses(before, plan, convert):
    """Map declared scene addresses only; axis labels and values stay literal."""
    def address(value):
        return convert(value) if value is not None else None
    before = tuple(replace(row,
        path=address(row.path), parent=address(row.parent),
        scale_sources=tuple(map(address, row.scale_sources)),
        stored_sources=tuple(map(address, row.stored_sources)),
        fk_parent_constraint=address(row.fk_parent_constraint),
        fk_parent_scale_sources=tuple(map(address, row.fk_parent_scale_sources)),
        fk_parent_compound_scale_source=address(row.fk_parent_compound_scale_source),
        fk_parent_extra_constraints=tuple(map(address, row.fk_parent_extra_constraints)),
        fk_parent_extra_scale_sources=tuple(tuple(map(address, sources)) for sources in row.fk_parent_extra_scale_sources),
        fk_parent_extra_compound_sources=tuple(map(address, row.fk_parent_extra_compound_sources))) for row in before)
    joints = []
    for row in plan.joints:
        axes = tuple(replace(axis, fk_parent_extra_scale_targets=tuple(map(address, axis.fk_parent_extra_scale_targets)),
            **{key: address(getattr(axis, key)) for key in (
            'scale_source', 'stored_source', 'reroute_source', 'disconnect_scale_source',
            'restore_source', 'compensation_source', 'parent_inverse_source', 'fk_parent_scale_target')})
            for axis in row.axes)
        joints.append(replace(row, path=address(row.path), axes=axes,
            compensation_node=address(row.compensation_node),
            parent_inverse_node=address(row.parent_inverse_node),
            fk_parent_disconnect_compound=address(row.fk_parent_disconnect_compound),
            fk_parent_extra_disconnect_compounds=tuple((address(source), address(target))
                for source, target in row.fk_parent_extra_disconnect_compounds)))
    nodes = tuple(replace(row, name=address(row.name),
        input1_sources=tuple(map(address, row.input1_sources)),
        input2_sources=tuple(map(address, row.input2_sources))) for row in plan.nodes)
    return before, replace(plan, joints=tuple(joints), nodes=nodes,
                           retired_joints=tuple(map(address, plan.retired_joints)))



def encode(before, plan):
    """Freeze the source calculation's topology separately from live addresses.

    Reparenting a Part later must move plugs, without recomputing the earlier
    native scaling branch against the new hierarchy.
    """
    basis_plan = replace(plan, retired_joints=())
    basis = dict(version=1, before=[asdict(row) for row in before], plan=asdict(basis_plan))
    _decode_v1(canonical(basis))
    return canonical(dict(version=2, basis=basis, addresses=[],
                          retired_joints=list(plan.retired_joints)))


def _declared_nodes(before, plan):
    nodes = set()
    def collect(address):
        nodes.add(address.partition('.')[0])
        return address
    map_addresses(before, plan, collect)
    return nodes


def _mapped(before, plan, addresses):
    def convert(address):
        node, separator, attribute = address.partition('.')
        return addresses.get(node, node) + (separator + attribute if separator else '')
    return map_addresses(before, plan, convert)


def _v2(text):
    raw = exact(safe_json(text), ('version', 'basis', 'addresses', 'retired_joints'))
    if type(raw['version']) is not int or raw['version'] != 2:
        raise CharacterRegistryError('Game Engine Scaling 来源版本无效')
    before, plan = _decode_v1(canonical(raw['basis']))
    if plan.retired_joints:
        raise CharacterRegistryError('Game Engine Scaling 计算基准不能删除关节')
    allowed = _declared_nodes(before, plan)
    pairs = raw['addresses']
    if (not isinstance(pairs, list) or len(pairs) > len(allowed)
            or any(not isinstance(pair, list) or len(pair) != 2
                   or any(not isinstance(value, str) or not value or '.' in value for value in pair)
                   or pair[0] not in allowed for pair in pairs)
            or len({pair[0] for pair in pairs}) != len(pairs)):
        raise CharacterRegistryError('Game Engine Scaling 地址交接记录无效')
    before, plan = _mapped(before, plan, dict(pairs))
    if (len({row.path for row in before}) != len(before)
            or len({row.name for row in plan.nodes}) != len(plan.nodes)):
        raise CharacterRegistryError('Game Engine Scaling 地址交接合并了不同源对象')
    retired = raw['retired_joints']
    if (not isinstance(retired, list) or any(not isinstance(path, str) for path in retired)
            or len(set(retired)) != len(retired) or not set(retired) <= {row.path for row in before}):
        raise CharacterRegistryError('Game Engine Scaling 已删除关节记录无效')
    return raw, before, replace(plan, retired_joints=tuple(retired))


def decode(text):
    raw = safe_json(text)
    if isinstance(raw, dict) and type(raw.get('version')) is int and raw['version'] == 3:
        _, before, plan, _ = _v3(text)
        return before, plan
    if isinstance(raw, dict) and type(raw.get('version')) is int and raw['version'] == 2:
        _, before, plan = _v2(text)
        return before, plan
    return _decode_v1(text)


def remap_record(text, convert):
    """Compose a real address handoff while keeping the source basis intact."""
    before, plan = decode(text)
    raw = safe_json(text)
    if raw['version'] == 1:
        raw = safe_json(encode(before, plan))
    basis_before, basis_plan = _decode_v1(canonical(raw['basis']))
    current = dict(raw['addresses'])
    pairs = []
    for original in sorted(_declared_nodes(basis_before, basis_plan)):
        actual = convert(current.get(original, original))
        if actual != original:
            pairs.append([original, actual])
    raw['addresses'] = pairs
    raw['retired_joints'] = [convert(path) for path in plan.retired_joints]
    if raw['version'] == 3:
        raw['frozen_inputs'] = [[convert(target.partition('.')[0]) + '.' + target.partition('.')[2], value]
                                for target, value in raw['frozen_inputs']]
    updated = canonical(raw)
    decode(updated)
    return updated


def mark_retired(text, paths):
    before, plan = decode(text)
    raw = safe_json(text)
    if raw['version'] == 1:
        raw = safe_json(encode(before, plan))
    known = {row.path for row in before}
    raw['retired_joints'] = list(dict.fromkeys((*plan.retired_joints, *sorted(known.intersection(paths)))))
    updated = canonical(raw)
    decode(updated)
    return updated



def replace_joint_uuids(text, current_uuids):
    """A Body replacement changes object identities, not the source calculation."""
    before, plan = decode(text)
    raw = safe_json(text)
    if raw['version'] == 1:
        raw = safe_json(encode(before, plan))
    actual = {row.path: row for row in before}
    addresses = dict(raw['addresses'])
    for row in raw['basis']['before']:
        path = addresses.get(row['path'], row['path'])
        if path in plan.retired_joints:
            continue
        if path not in actual or path not in current_uuids:
            raise CharacterRegistryError('Game Engine Scaling 重建缺少原关节对应对象')
        identity = current_uuids[path]
        if not isinstance(identity, str) or not identity:
            raise CharacterRegistryError('Game Engine Scaling 重建关节身份无效')
        row['uuid'] = identity
    updated = canonical(raw)
    decode(updated)
    return updated


def _v3(text):
    """Record only cached MPD inputs disconnected by native joint deletion.

    The calculation basis remains version 1, and its exact source branch is
    still checked. A frozen input is valid only when that basis input was
    driven by an explicitly retired joint; this is no general graph override.
    """
    raw = exact(safe_json(text), ('version', 'basis', 'addresses', 'retired_joints', 'frozen_inputs'))
    if type(raw['version']) is not int or raw['version'] != 3:
        raise CharacterRegistryError('Game Engine Scaling 来源版本无效')
    base = {key: value for key, value in raw.items() if key != 'frozen_inputs'}
    base['version'] = 2
    _, before, plan = _v2(canonical(base))
    allowed = {}
    retired = set(plan.retired_joints)
    for node in plan.nodes:
        for kind in ('input1', 'input2'):
            for axis, source in zip('XYZ', getattr(node, kind + '_sources')):
                if source and source.partition('.')[0] in retired:
                    allowed[node.name + '.' + kind + axis] = source
    rows = raw['frozen_inputs']
    if (not isinstance(rows, list) or len(rows) > len(allowed)
            or any(not isinstance(row, list) or len(row) != 2
                   or not isinstance(row[0], str) or row[0] not in allowed
                   or type(row[1]) not in (float, int) or not isfinite(row[1]) for row in rows)
            or len({row[0] for row in rows}) != len(rows)):
        raise CharacterRegistryError('Game Engine Scaling 删除驱动后的输入缓存无效')
    return raw, before, plan, tuple((row[0], float(row[1])) for row in rows)


def frozen_inputs(text):
    """Read captured values without pretending older records contain them."""
    raw = safe_json(text)
    if isinstance(raw, dict) and type(raw.get('version')) is int and raw['version'] == 3:
        return _v3(text)[3]
    decode(text)
    return ()


def freeze_retired_inputs(text, values):
    """Upgrade the record after reading the actual retained Maya MPD values."""
    before, plan = decode(text)
    raw = safe_json(text)
    if raw['version'] == 1:
        raw = safe_json(encode(before, plan))
    previous = dict(frozen_inputs(text))
    previous.update(dict(values))
    raw['version'] = 3
    raw['frozen_inputs'] = [[target, value] for target, value in sorted(previous.items())]
    updated = canonical(raw)
    _v3(updated)
    return updated


def live_node_plan(plan, inputs):
    """Leave orphan MPDs intact, replacing only captured deleted input edges."""
    frozen = {target for target, _ in inputs}
    nodes = []
    for node in plan.nodes:
        changes = {kind + '_sources': tuple(None if node.name + '.' + kind + axis in frozen else source
            for axis, source in zip('XYZ', getattr(node, kind + '_sources')))
            for kind in ('input1', 'input2')}
        nodes.append(replace(node, **changes))
    return replace(plan, nodes=tuple(nodes))
