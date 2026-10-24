"""MEL rebuild's retained external connections for a native MoCap session.

The original constraint, Pole helper, pairBlend and animation objects survive.
The normal extension transfer moves their exact edges and DAG parents. This
module only verifies/rebases the ownership document against the independently
audited old/new generated UUID pairs; it never bakes or recreates business DG.
"""
from dataclasses import replace

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_name_matcher_session import (
    ATTRIBUTE, decode_session, encode_session, rebase_session)
from .maya_source_name_matcher_session import (
    _commands, _capture, _node, audit, session_group)
from .maya_driving_registration import _write_string


def capture(host):
    group = session_group(host)
    if group is None:
        return None
    audit(host)
    return encode_session(decode_session(_commands(host).getAttr(group + '.' + ATTRIBUTE)))


def sample_frames(host,document):
    """Read external source keys without adopting or moving their curves."""
    if document is None:return ()
    saved=decode_session(document);c=_commands(host)
    owned={saved['group']['uuid'],*(row['uuid'] for row in saved['nodes']),
           *(row['uuid'] for row in saved['receivers'])}
    # Inputs on a natively deleted blend are historical provenance. Its old
    # time curves may also have been deleted; neither object is a live source
    # to sample or a node that a later rebuild must resurrect.
    live_nodes=tuple(row for row in saved['nodes']
        if row['uuid'] not in saved.get('removed_blends',()))
    pending={edge['source_uuid'] for row in live_nodes for edge in row['inputs']}-owned
    seen=set();frames=set()
    for identity in pending:
        path,_=_live(c,identity)
        if 'dagNode' not in (c.nodeType(path,inherited=True) or ()):
            continue
        while path is not None and path not in seen:
            seen.add(path)
            frames.update(float(frame) for frame in c.keyframe(path,query=True,timeChange=True) or ())
            parents=c.listRelatives(path,parent=True,fullPath=True) or ()
            path=parents[0] if parents else None
    frames.update(float(c.playbackOptions(query=True,**{flag:True})) for flag in ('minTime','maxTime'))
    return tuple(sorted(frames))


def retained_nodes(host, document, native=()):
    c = _commands(host)
    rows=[]
    if document is not None:
        saved=decode_session(document)
        rows.extend((saved['group'], *(row for row in saved['nodes']
            if row['uuid'] not in saved.get('removed_blends', ()))))
    from adv_py.core.source_native_animation import decode_native_animation
    rows.extend(decode_native_animation(text)['node'] for text in native)
    result = []
    for row in rows:
        if _node(c, row['path']) != (row['path'], row['uuid']):
            raise CharacterRegistryError('动捕重建保留对象身份变化：' + row['path'])
        result.append(host._cmds.identity.to_local(row['path'])
            if hasattr(host._cmds, 'identity') else row['path'])
    return tuple(result)


def extension_without_document(row, document, native=()):
    """The dynamic UUID manifest has its own exact handoff verification."""
    excluded=set()
    if document is not None and row.uuid==decode_session(document)['group']['uuid']:
        excluded.add(ATTRIBUTE)
    from adv_py.core.source_native_animation import ATTRIBUTE as NATIVE_ATTRIBUTE,decode_native_animation
    if any(row.uuid==decode_native_animation(text)['node']['uuid'] for text in native):
        excluded.add(NATIVE_ATTRIBUTE)
    return replace(row,attributes=tuple(attribute for attribute in row.attributes
        if attribute[0] not in excluded)) if excluded else row


def _live(c, identity):
    matches = c.ls(identity, long=True) or ()
    if len(matches) != 1:
        raise CharacterRegistryError('动捕重建交接 UUID 缺失或歧义：' + identity)
    return _node(c, matches[0])


def _replacements(host,staged,referenced,removed=()):
    if staged.ownership is None:
        raise CharacterRegistryError('动捕交接缺少生成图 UUID 审计')
    c=_commands(host)
    deleted={identity for _,identity,_ in staged.ownership.removed_nodes}
    if referenced & deleted:
        raise CharacterRegistryError('Spline 数量变更删除了正在动捕连接或原生动画保留的端点')
    paired={old:(new,kind) for _,old,new,kind in staged.ownership.nodes}
    replacements={}
    for old in referenced-set(removed):
        identity,kind=paired.get(old,(old,None))
        path,identity=_live(c,identity)
        if kind is not None and c.nodeType(path)!=kind:
            raise CharacterRegistryError('动捕交接的替换节点类型变化：'+path)
        replacements[old]=(path,identity)
    return replacements


def expected(host, staged):
    document = staged.original.mocap_session
    if document is None:
        return None
    saved = decode_session(document)
    c = _commands(host)
    referenced = {saved['group']['uuid']}
    for row in (*saved['nodes'], *saved['receivers']):
        if row['uuid'] in saved.get('removed_blends',()):
            continue
        referenced.add(row['uuid'])
        if row.get('parent') is not None:
            referenced.add(row['parent'])
        referenced.update(edge['source_uuid'] for edge in row['inputs'])
    replacements=_replacements(host,staged,referenced,saved.get('removed_blends',()))
    return rebase_session(saved, replacements)


def expected_native(host,staged):
    from adv_py.core.source_native_animation import decode_native_animation,rebase_native_animation
    rows=[]
    for document in getattr(staged.original,'native_animation',()):
        value=decode_native_animation(document)
        referenced={value['node']['uuid'],*(row['uuid'] for row in value['receivers'])}
        referenced.update(edge['source_uuid'] for row in (value['node'],*value['receivers'])
            for edge in row['inputs'])
        rows.append(rebase_native_animation(value,_replacements(host,staged,referenced)))
    return tuple(rows)


def verify(host, staged):
    from .maya_source_native_animation import verify_record
    for value in expected_native(host,staged):
        verify_record(host,value)
    wanted = expected(host, staged)
    if wanted is None:
        return
    c = _commands(host)
    group, identity = _live(c, wanted['group']['uuid'])
    if wanted['group'] != dict(path=group, uuid=identity):
        raise CharacterRegistryError('动捕交接组地址或 UUID 变化')
    plug = group + '.' + ATTRIBUTE
    if not c.getAttr(plug, lock=True) or decode_session(c.getAttr(plug)) != wanted:
        raise CharacterRegistryError('动捕交接文档不是明确 UUID 交接的结果')
    for row in wanted['nodes']:
        if row['uuid'] in wanted.get('removed_blends', ()):
            if c.objExists(row['path']) or c.ls(row['uuid'], long=True):
                raise CharacterRegistryError('动捕交接重新出现烘焙已删除的 pairBlend')
        elif _capture(c, row['path']) != row:
            raise CharacterRegistryError('动捕交接改变了原辅助节点、目标或输入：' + row['path'])
    for row in wanted['receivers']:
        if _node(c, row['path']) != (row['path'], row['uuid']):
            raise CharacterRegistryError('动捕交接接收控制器身份不一致')
        for edge in row['inputs']:
            live = c.connectionInfo(row['path'] + '.' + edge['destination'],
                                    sourceFromDestination=True)
            if live:
                from .maya_source_name_matcher_session import _plug
                if _plug(c, live) != (edge['source'], edge['source_uuid']):
                    # Native Bake can leave a direct animation curve instead
                    # of an owned constraint output. Character validation
                    # verifies the actual remaining time-curve boundary.
                    source_node,attribute=live.split('.',1)
                    identities=c.ls(source_node,uuid=True) or ()
                    preserved={curve.uuid for curve in staged.original.curves}
                    if (attribute!='output' or len(identities)!=1 or identities[0] not in preserved
                            or c.nodeType(source_node) not in ('animCurveTA','animCurveTL','animCurveTU')):
                        raise CharacterRegistryError('动捕交接控制器接线变化')


def install(host, staged):
    """Called only after the normal transfer/promote has moved actual edges."""
    host._require_transaction()
    from adv_py.core.source_native_animation import ATTRIBUTE as NATIVE_ATTRIBUTE,encode_native_animation
    from .maya_source_native_animation import _settings,verify_record
    for value in expected_native(host,staged):
        c=_commands(host);node=value['node']
        if _capture(c,node['path'])!=node or _settings(c,node['path'])!=value['settings']:
            raise CharacterRegistryError('原生动捕动画实际交接图或缓存值变化')
        plug=node['path']+'.'+NATIVE_ATTRIBUTE
        _write_string(c,plug,encode_native_animation(value));c.setAttr(plug,lock=True)
        verify_record(host,value)
    wanted = expected(host, staged)
    if wanted is None:
        return
    c = _commands(host)
    for row in wanted['nodes']:
        if row['uuid'] in wanted.get('removed_blends', ()):
            continue
        if _capture(c, row['path']) != row:
            raise CharacterRegistryError('动捕实际交接图与原 UUID 交接计划不一致：' + row['path'])
    group, _ = _live(c, wanted['group']['uuid'])
    plug = group + '.' + ATTRIBUTE
    _write_string(c, plug, encode_session(wanted))
    c.setAttr(plug, lock=True)
    verify(host, staged)
