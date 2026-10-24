"""Bounded metadata handoff for original Controls -> ExtraControls rewiring.

Only the native business operation connects/disconnects DG. This observer
requires the exact captured driver UUID and the exact two controller UUIDs.
"""
from copy import deepcopy
from dataclasses import dataclass
from adv_py.core.character_registry import CharacterRegistryError,canonical
from adv_py.core.source_name_matcher_session import ATTRIBUTE, decode_session, encode_session
from adv_py.core.source_native_animation import (
    ATTRIBUTE as NATIVE_ATTRIBUTE, decode_native_animation, encode_native_animation)
from .maya_source_name_matcher_session import _commands, _node, _plug, audit, session_group
from .maya_source_native_animation import capture as capture_native, verify_record
from .maya_driving_registration import _write_string


@dataclass(frozen=True)
class AnimationPortMove:
    source: str
    source_uuid: str
    destination: str
    destination_uuid: str
    driver: str
    driver_uuid: str


@dataclass(frozen=True)
class AnimationPortMoveBoundary:
    session: dict | None
    native: tuple
    moves: tuple[AnimationPortMove, ...]
    quick: tuple=()


def capture(host, ports):
    c = _commands(host)
    audit(host)
    group = session_group(host)
    saved = decode_session(c.getAttr(group + '.' + ATTRIBUTE)) if group else None
    native = tuple(decode_native_animation(text) for text in capture_native(host))
    from .maya_original_quick_ik_state import capture as capture_quick
    quick=tuple(deepcopy(value) for value in capture_quick(host))
    moves = []
    destinations = set()
    for source, destination in ports:
        source, source_uuid = _plug(c, source)
        destination, destination_uuid = _plug(c, destination)
        if source == destination or source.split('.', 1)[1] != destination.split('.', 1)[1]:
            raise CharacterRegistryError('原版动画迁移必须保留对应通道轴向')
        if destination in destinations:
            raise CharacterRegistryError('原版动画迁移接收端口重复')
        destinations.add(destination)
        driver = c.connectionInfo(source, sourceFromDestination=True)
        if not driver:
            continue
        driver, driver_uuid = _plug(c, driver)
        if c.connectionInfo(destination, sourceFromDestination=True):
            raise CharacterRegistryError('原版动画迁移 Extra 接收端口已被占用：' + destination)
        moves.append(AnimationPortMove(source, source_uuid, destination,
                                       destination_uuid, driver, driver_uuid))
    return AnimationPortMoveBoundary(saved,native,tuple(moves),quick)


def _receivers(rows, moves):
    """Split/merge actual receiver rows, retaining every untouched source edge."""
    by_source = {move.source: move for move in moves}
    receivers = {}
    for row in rows:
        for edge in row['inputs']:
            move = by_source.get(row['path'] + '.' + edge['destination'])
            if move is not None and (edge['source'], edge['source_uuid']) == (move.driver, move.driver_uuid):
                path = move.destination.split('.', 1)[0]
                identity = move.destination_uuid
            else:
                path, identity = row['path'], row['uuid']
            item = receivers.setdefault(identity, dict(path=path, uuid=identity, inputs=[]))
            if item['path'] != path or any(old['destination'] == edge['destination'] for old in item['inputs']):
                raise CharacterRegistryError('原版动画迁移产生重复接收端口')
            item['inputs'].append(deepcopy(edge))
    return list(receivers.values())


def finish(host, boundary):
    host._require_transaction()
    c = _commands(host)
    for move in boundary.moves:
        if _plug(c, move.source) != (move.source, move.source_uuid) or _plug(c, move.destination) != (move.destination, move.destination_uuid):
            raise CharacterRegistryError('原版动画迁移控制器身份变化')
        if c.connectionInfo(move.source, sourceFromDestination=True):
            raise CharacterRegistryError('原版动画迁移原通道仍然受驱动')
        source = c.connectionInfo(move.destination, sourceFromDestination=True)
        if not source or _plug(c, source) != (move.driver, move.driver_uuid):
            raise CharacterRegistryError('原版动画迁移接到了其他驱动节点')
    if boundary.session is not None:
        saved = boundary.session
        plug = saved['group']['path'] + '.' + ATTRIBUTE
        if (_node(c,saved['group']['path']) != (saved['group']['path'],saved['group']['uuid'])
                or not c.getAttr(plug,lock=True) or decode_session(c.getAttr(plug)) != saved):
            raise CharacterRegistryError('原版动画迁移期间动捕会话身份或锁定文档变化')
        updated = {**saved, 'receivers': _receivers(saved['receivers'], boundary.moves)}
        _write_string(c, plug, encode_session(updated)); c.setAttr(plug, lock=True)
        audit(host)
    for saved in boundary.native:
        plug = saved['node']['path'] + '.' + NATIVE_ATTRIBUTE
        if (_node(c,saved['node']['path']) != (saved['node']['path'],saved['node']['uuid'])
                or not c.getAttr(plug,lock=True) or decode_native_animation(c.getAttr(plug)) != saved):
            raise CharacterRegistryError('原版动画迁移期间原生动画身份或锁定文档变化')
        updated = {**saved, 'receivers': _receivers(saved['receivers'], boundary.moves)}
        _write_string(c, plug, encode_native_animation(updated)); c.setAttr(plug, lock=True)
        verify_record(host, updated)
    from adv_py.core.source_quick_ik import ATTRIBUTE as QUICK_ATTRIBUTE,decode_quick_ik
    from .maya_original_quick_ik_state import _audit as audit_quick
    for saved in boundary.quick:
        group=saved['group']
        plug=group['path']+'.'+QUICK_ATTRIBUTE
        if (_node(c,group['path'])!=(group['path'],group['uuid'])
                or not c.getAttr(plug,lock=True) or decode_quick_ik(c.getAttr(plug))!=saved):
            raise CharacterRegistryError('原版动画迁移期间 QuickIK 图记录变化或解锁')
        updated={**saved,'receivers':_receivers(saved['receivers'],boundary.moves)}
        _write_string(c,plug,canonical(updated));c.setAttr(plug,lock=True)
        audit_quick(c,updated)
