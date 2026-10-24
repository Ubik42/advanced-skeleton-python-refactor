"""Observe original static-channel deletion without editing animation DG.

The document refresh is bounded by a graph snapshot taken immediately before
Maya's native delete. It can forget a genuinely deleted time curve or pairBlend;
it cannot authorize a replacement node, a new driver or an unrelated rewire.
"""
from dataclasses import dataclass

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_name_matcher_session import (
    ATTRIBUTE as SESSION_ATTRIBUTE, decode_session, encode_session)
from adv_py.core.source_native_animation import (
    ATTRIBUTE as NATIVE_ATTRIBUTE, decode_native_animation, encode_native_animation)
from .maya_source_name_matcher_session import (
    _commands, _capture, _node, _plug, session_group, audit as audit_session)
from .maya_source_native_animation import (
    _settings, _time_curve, capture as capture_native, verify_record)
from .maya_driving_registration import _write_string


@dataclass(frozen=True)
class StaticBlendBoundary:
    node: dict
    values: tuple
    curves: frozenset[str]


@dataclass(frozen=True)
class StaticAnimationBoundary:
    session: dict | None
    native: tuple
    blends: tuple[StaticBlendBoundary,...]
    receivers: tuple
    direct_curves: frozenset[str]
    quick: object | None = None


def _value(value):
    if isinstance(value,(tuple,list)):
        return tuple(number for item in value for number in _value(item))
    return (value,)


def capture(host):
    """Freeze actual identities, native time inputs and current receiver edges."""
    c=_commands(host)
    audit_session(host)
    group=session_group(host)
    saved=decode_session(c.getAttr(group+'.'+SESSION_ATTRIBUTE)) if group else None
    native=tuple(decode_native_animation(document) for document in capture_native(host))
    records=tuple(saved['nodes']) if saved else ()
    records+=tuple(row['node'] for row in native)
    blends=[]
    identities=set()
    for row in records:
        if row['kind']!='pairBlend' or saved and row['uuid'] in saved.get('removed_blends',()):
            continue
        if row['uuid'] in identities:
            raise CharacterRegistryError('原生动画静态清理发现重复 pairBlend 所有权')
        identities.add(row['uuid'])
        current=_capture(c,row['path'])
        if current!=row:
            raise CharacterRegistryError('原生动画静态清理前 pairBlend 已变化')
        attributes=tuple('in'+kind+axis+index for kind in ('Translate','Rotate')
            for index in ('1','2') for axis in 'XYZ')
        attributes+=('weight','rotInterpolation','rotateMode','translateXMode','translateYMode','translateZMode')
        values=tuple((attribute,_value(c.getAttr(row['path']+'.'+attribute)))
            for attribute in attributes if c.objExists(row['path']+'.'+attribute))
        curves=frozenset(edge['source_uuid'] for edge in row['inputs']
            if _time_curve(c,edge['source']))
        blends.append(StaticBlendBoundary(current,values,curves))
    receivers={}
    direct_curves=set()
    for document in ((saved,) if saved else ())+native:
        for row in document['receivers']:
            if _node(c,row['path'])!=(row['path'],row['uuid']):
                raise CharacterRegistryError('原生动画静态清理前接收控制器身份变化')
            for edge in row['inputs']:
                destination=row['path']+'.'+edge['destination']
                source=c.connectionInfo(destination,sourceFromDestination=True)
                current=_plug(c,source) if source else None
                if source and _time_curve(c,source):direct_curves.add(current[1])
                receivers[(row['path'],row['uuid'],edge['destination'])]=current
    from .maya_original_quick_ik_animation import capture as capture_quick
    return StaticAnimationBoundary(saved,native,tuple(blends),tuple(receivers.items()),frozenset(direct_curves),capture_quick(host))


def _refresh_blend(c,row):
    old=row.node
    matches=c.ls(old['uuid'],long=True) or ()
    if not matches:
        if c.objExists(old['path']):
            raise CharacterRegistryError('静态清理后原 pairBlend 被同名节点替换')
        return None
    if matches!=[old['path']]:
        raise CharacterRegistryError('静态清理改变了原 pairBlend 地址或身份')
    current=_capture(c,old['path'])
    if any(current[key]!=old[key] for key in ('path','uuid','kind','parent')):
        raise CharacterRegistryError('静态清理改变了原 pairBlend 身份或类型')
    if any(edge not in old['inputs'] for edge in current['inputs']):
        raise CharacterRegistryError('静态清理为原 pairBlend 增加或替换了输入')
    for edge in old['inputs']:
        if edge in current['inputs']:continue
        if edge['source_uuid'] not in row.curves or c.ls(edge['source_uuid'],long=True):
            raise CharacterRegistryError('静态清理断开了未删除的原输入或非时间动画输入')
    expected=dict(row.values)
    for item in _settings(c,old['path']):
        if _value(item['value'])!=expected.get(item['attribute']):
            raise CharacterRegistryError('静态清理改变了原 pairBlend 原生缓存值')
    return current


def _collapsed_sources(row,attribute):
    channel='Translate' if attribute.startswith('translate') else 'Rotate'
    axis=attribute[-1]
    result=set()
    for edge in row.node['inputs']:
        for index in ('1','2'):
            if edge['destination']=='in'+channel+axis+index:
                result.add((edge['source'],edge['source_uuid']))
            elif edge['destination']=='in'+channel+index:
                source,plug=edge['source'].split('.',1)
                if plug=='constraint'+channel:
                    result.add((source+'.'+plug+axis,edge['source_uuid']))
    return result


def finish(host,boundary):
    """Refresh metadata only after the native operation in this transaction."""
    host._require_transaction()
    c=_commands(host)
    refreshed={row.node['uuid']:_refresh_blend(c,row) for row in boundary.blends}
    original={row.node['uuid']:row for row in boundary.blends}
    for (path,identity,attribute),previous in boundary.receivers:
        if _node(c,path)!=(path,identity):
            raise CharacterRegistryError('静态清理改变了接收控制器身份')
        source=c.connectionInfo(path+'.'+attribute,sourceFromDestination=True)
        current=_plug(c,source) if source else None
        if current==previous:continue
        if previous and previous[1] in original:
            row=original[previous[1]]
            if refreshed[previous[1]] is not None:
                raise CharacterRegistryError('静态清理断开了仍存在的原 pairBlend 输出')
            if current is not None and current not in _collapsed_sources(row,attribute):
                raise CharacterRegistryError('静态清理折叠 pairBlend 后出现非原输入驱动')
        elif previous:
            # A receiver already baked to a direct curve can become static.
            # A live constraint or unrelated input cannot disappear here.
            if current is not None or c.ls(previous[1],long=True):
                raise CharacterRegistryError('静态清理替换了原接收输入或断开存活驱动')
            # The pre-operation snapshot proves the node kind below; never
            # infer that a deleted, similarly named object was an animCurve.
            if previous[1] not in boundary.direct_curves:
                raise CharacterRegistryError('静态清理删除了非原时间动画接收输入')
        else:
            raise CharacterRegistryError('静态清理为原静态接收端口增加了驱动')
    if boundary.session is not None:
        saved=boundary.session
        plug=saved['group']['path']+'.'+SESSION_ATTRIBUTE
        if (_node(c,saved['group']['path'])!=(saved['group']['path'],saved['group']['uuid'])
                or not c.getAttr(plug,lock=True) or decode_session(c.getAttr(plug))!=saved):
            raise CharacterRegistryError('静态清理期间原动捕会话登记变化')
        removed=list(saved.get('removed_blends',()))
        nodes=[]
        for row in saved['nodes']:
            if row['uuid'] in refreshed:
                current=refreshed[row['uuid']]
                if current is None:
                    removed.append(row['uuid']);nodes.append(row)
                else:nodes.append(current)
            else:nodes.append(row)
        if saved['version']>=2:
            receivers=[]
            for row in saved['receivers']:
                inputs=[]
                for edge in row['inputs']:
                    source=c.connectionInfo(row['path']+'.'+edge['destination'],sourceFromDestination=True)
                    actual=_plug(c,source) if source else None
                    if (edge['source_uuid'] in refreshed and refreshed[edge['source_uuid']] is None
                            and actual and actual[1]==edge['constraint_uuid']):
                        edge={**edge,'source':actual[0],'source_uuid':actual[1]}
                    inputs.append(edge)
                receivers.append({**row,'inputs':inputs})
            updated={**saved,'version':3,'static_cleaned':True,'nodes':nodes,
                'removed_blends':list(dict.fromkeys(removed)),'receivers':receivers}
            _write_string(c,plug,encode_session(updated));c.setAttr(plug,lock=True)
        audit_session(host)
    for saved in boundary.native:
        current=refreshed[saved['node']['uuid']]
        if current is None:continue
        plug=current['path']+'.'+NATIVE_ATTRIBUTE
        if not c.getAttr(plug,lock=True) or decode_native_animation(c.getAttr(plug))!=saved:
            raise CharacterRegistryError('静态清理期间保留动画登记变化')
        updated={**saved,'node':current,'settings':_settings(c,current['path'])}
        _write_string(c,plug,encode_native_animation(updated));c.setAttr(plug,lock=True)
        verify_record(host,updated)
    if boundary.quick is not None:
        from .maya_original_quick_ik_animation import finish as finish_quick
        ports=frozenset((row['uuid'],edge['destination'])
            for value in boundary.quick.records for row in value['receivers'] for edge in row['inputs'])
        finish_quick(host,boundary.quick,ports,static=True)
