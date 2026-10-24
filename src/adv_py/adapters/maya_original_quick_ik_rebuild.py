"""Retain original QuickIK objects through the existing UUID rebuild handoff."""
from copy import deepcopy
from dataclasses import replace

from adv_py.core.character_registry import CharacterRegistryError, canonical
from adv_py.core.source_quick_ik import ATTRIBUTE, decode_quick_ik, rebase_quick_ik
from .maya_original_quick_ik_state import capture as capture_state, _snapshot, _audit
from .maya_source_name_matcher_session import _commands, _node
from .maya_source_mocap_rebuild import _replacements
from .maya_driving_registration import _write_string


def capture(host):
    c = _commands(host)
    documents = []
    for original in capture_state(host):
        value = deepcopy(original)
        # Include newly keyed native QuickIK channels in the handoff snapshot.
        # The source graph and its on-node manifest are not modified here.
        value['nodes'] = [_snapshot(c, row['path']) for row in value['nodes']]
        documents.append(canonical(value))
    return tuple(documents)


def retained_nodes(host, documents):
    c = _commands(host)
    result = []
    for document in documents:
        for row in decode_quick_ik(document)['nodes']:
            if _node(c, row['path']) != (row['path'], row['uuid']):
                raise CharacterRegistryError('QuickIK 重建保留对象身份变化：' + row['path'])
            local = host._cmds.identity.to_local(row['path']) if hasattr(host._cmds, 'identity') else row['path']
            result.append(local)
    return tuple(dict.fromkeys(result))


def extension_without_document(row, documents):
    if any(row.uuid == decode_quick_ik(text)['group']['uuid'] for text in documents):
        return replace(row, attributes=tuple(value for value in row.attributes if value[0] != ATTRIBUTE))
    return row


def sample_frames(host, documents):
    c = _commands(host)
    frames = set()
    seen=set()
    for document in documents:
        saved=decode_quick_ik(document)
        identities={row['uuid'] for row in (*saved['nodes'],*saved['receivers'])}
        identities.update(edge['source_uuid'] for row in saved['nodes'] for edge in row['inputs'])
        for identity in identities:
            matches=c.ls(identity,long=True) or ()
            if len(matches)!=1:
                raise CharacterRegistryError('QuickIK 重建采样来源 UUID 缺失或歧义：'+identity)
            path=matches[0]
            # A key on the existing QuickIK root or a parent of the source
            # constraint target also changes the evaluated temporary rig.
            # Sample those native times without adopting or moving the source.
            while path is not None and path not in seen:
                seen.add(path)
                frames.update(float(frame) for frame in c.keyframe(path,query=True,timeChange=True) or ())
                parents=c.listRelatives(path,parent=True,fullPath=True) or ()
                path=parents[0] if parents else None
    if documents:
        frames.update(float(c.playbackOptions(query=True, **{flag: True})) for flag in ('minTime', 'maxTime'))
    return tuple(sorted(frames))


def expected(host, staged):
    result = []
    for document in getattr(staged.original, 'quick_ik', ()):
        saved = decode_quick_ik(document)
        referenced = {saved['group']['uuid']}
        for row in (*saved['nodes'], *saved['receivers']):
            referenced.add(row['uuid'])
            if row.get('parent') is not None:
                referenced.add(row['parent'])
            referenced.update(edge['source_uuid'] for edge in row['inputs'])
        result.append(rebase_quick_ik(saved, _replacements(host, staged, referenced)))
    return tuple(result)


def verify(host, staged):
    c = _commands(host)
    for value in expected(host, staged):
        _audit(c, value)


def install(host, staged):
    host._require_transaction()
    c = _commands(host)
    for value in expected(host, staged):
        for row in value['nodes']:
            if _snapshot(c, row['path']) != row:
                raise CharacterRegistryError('QuickIK 实际交接图与原 UUID 对应不同：' + row['path'])
        plug = value['group']['path'] + '.' + ATTRIBUTE
        _write_string(c, plug, canonical(value))
        c.setAttr(plug, lock=True)
        _audit(c, value)
