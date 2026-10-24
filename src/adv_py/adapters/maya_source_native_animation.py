"""Observe native surviving pairBlends; never create or edit animation DG."""
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.source_native_animation import (
    ATTRIBUTE, FORMAT, decode_native_animation, encode_native_animation)
from .maya_source_name_matcher_session import _commands, _capture, _node, _plug
from .maya_driving_registration import _write_string


def _settings(c,node):
    names = tuple('in'+kind+axis+index
        for kind in ('Translate','Rotate') for index in ('1','2') for axis in 'XYZ')
    names += ('weight','rotInterpolation','rotateMode','translateXMode','translateYMode','translateZMode')
    rows = []
    for attribute in names:
        plug = node+'.'+attribute
        if not c.objExists(plug) or c.connectionInfo(plug,sourceFromDestination=True):
            continue
        rows.append(dict(attribute=attribute,value=c.getAttr(plug)))
    return rows


def _time_curve(c,source):
    node,attribute=source.split('.',1)
    if attribute != 'output' or c.nodeType(node) not in ('animCurveTA','animCurveTL','animCurveTU'):
        return False
    driver=c.connectionInfo(node+'.input',sourceFromDestination=True)
    return not driver or (driver.split('.',1)[1]=='outTime'
        and c.nodeType(driver.split('.',1)[0])=='time')


def observe_disconnect(host,saved):
    """MEL deletes output constraints and the group. Record what Maya kept.

    Some native Maya graphs retain an animation pairBlend. Its original
    animation and any native cached second input remain as Maya left them.
    A locked document on that existing object allows later save/rebuild audit.
    """
    host._require_transaction()
    c = _commands(host)
    if c.ls(saved['group']['uuid'],long=True):
        raise CharacterRegistryError('断开动捕后原约束组仍存在')
    outputs = (saved.get('output_constraints') or sorted({edge['source_uuid']
        for row in saved['receivers'] for edge in row['inputs']}))
    if any(c.ls(identity,long=True) for identity in outputs):
        raise CharacterRegistryError('断开动捕后原输出约束仍存在')
    for old in saved['nodes']:
        if old['kind'] != 'pairBlend':
            continue
        matches = c.ls(old['uuid'],long=True) or ()
        if not matches:
            continue
        if len(matches) != 1:
            raise CharacterRegistryError('断开动捕后原 pairBlend 身份歧义')
        current = _capture(c,matches[0])
        if current['uuid'] != old['uuid'] or current['kind'] != 'pairBlend':
            raise CharacterRegistryError('断开动捕后原 pairBlend 被替换')
        for edge in current['inputs']:
            if edge not in old['inputs'] and not _time_curve(c,edge['source']):
                raise CharacterRegistryError('断开动捕为原 pairBlend 增加了非原生动画输入')
        receivers=[]
        for receiver in saved['receivers']:
            if _node(c,receiver['path']) != (receiver['path'],receiver['uuid']):
                raise CharacterRegistryError('断开动捕时接收控制器被替换')
            edges=[]
            for edge in receiver['inputs']:
                if edge['source_uuid'] != old['uuid']:
                    continue
                source=c.connectionInfo(receiver['path']+'.'+edge['destination'],sourceFromDestination=True)
                if source and _plug(c,source)[1] == old['uuid']:
                    source,identity = _plug(c,source)
                    edges.append(dict(destination=edge['destination'],source=source,source_uuid=identity))
            if edges:
                receivers.append(dict(path=receiver['path'],uuid=receiver['uuid'],inputs=edges))
        if not receivers:
            continue
        plug=current['path']+'.'+ATTRIBUTE
        if c.objExists(plug):
            raise CharacterRegistryError('原生动画记录属性已被占用：'+plug)
        value=dict(format=FORMAT,version=1,origin=saved['group']['uuid'],node=current,
                   settings=_settings(c,current['path']),receivers=receivers)
        c.addAttr(current['path'],longName=ATTRIBUTE,dataType='string')
        _write_string(c,plug,encode_native_animation(value))
        c.setAttr(plug,lock=True)
        verify_record(host,value)


def verify_record(host,value):
    c=_commands(host)
    node=value['node']
    if _capture(c,node['path']) != node or _settings(c,node['path']) != value['settings']:
        raise CharacterRegistryError('保留的原生动捕动画节点、接线或缓存值变化')
    plug=node['path']+'.'+ATTRIBUTE
    if not c.getAttr(plug,lock=True) or decode_native_animation(c.getAttr(plug)) != value:
        raise CharacterRegistryError('保留的原生动捕动画记录变化或解锁')
    receivers={}
    for row in value['receivers']:
        if _node(c,row['path']) != (row['path'],row['uuid']):
            raise CharacterRegistryError('原生动捕动画的接收控制器身份变化')
        for edge in row['inputs']:
            destination=row['path']+'.'+edge['destination']
            source=c.connectionInfo(destination,sourceFromDestination=True)
            if not source or _plug(c,source) != (edge['source'],edge['source_uuid']):
                raise CharacterRegistryError('原生动捕动画的接收接线变化')
            receivers[destination]=edge
    for prefix in ('outTranslate','outRotate'):
        for axis in 'XYZ':
            source=node['path']+'.'+prefix+axis
            for destination in c.listConnections(source,source=False,destination=True,plugs=True) or ():
                destination,_=_plug(c,destination)
                edge=receivers.get(destination)
                if edge is None or _plug(c,source) != (edge['source'],edge['source_uuid']):
                    raise CharacterRegistryError('原生动捕动画被接到未登记的接收器')
    return frozenset((row['uuid'],edge['destination'],node['uuid'],edge['source'].split('.',1)[1])
        for row in value['receivers'] for edge in row['inputs'])


def capture(host):
    c=_commands(host)
    identity=getattr(host._cmds,'identity',None)
    rows=[]
    for node in c.ls('*.'+ATTRIBUTE,objectsOnly=True,long=True,recursive=True) or ():
        value=decode_native_animation(c.getAttr(node+'.'+ATTRIBUTE))
        if identity is not None and not all(identity.owns(row['path']) for row in value['receivers']):
            continue
        if _node(c,node) != (value['node']['path'],value['node']['uuid']):
            raise CharacterRegistryError('原生动捕动画记录被复制到另一节点')
        verify_record(host,value)
        rows.append(encode_native_animation(value))
    return tuple(sorted(rows))


def audit(host):
    edges=set()
    for document in capture(host):
        value=decode_native_animation(document)
        edges.update((row['uuid'],edge['destination'],value['node']['uuid'],
            edge['source'].split('.',1)[1]) for row in value['receivers'] for edge in row['inputs'])
    return frozenset(edges)


def reconnect_records(host,plan,*,remove=False):
    """Only retire metadata when its entire output joins the new session."""
    c=_commands(host)
    ports={(host.scene_address(link.control),kind+axis)
        for link in plan.links for kind,enabled in (('translate',link.point),('rotate',link.orient))
        if enabled for axis in 'XYZ'}
    ports.update((host.scene_address(pole.control),'translate'+axis)
        for pole in plan.poles for axis in 'XYZ')
    selected=[]
    for document in capture(host):
        value=decode_native_animation(document)
        owned={(row['path'],edge['destination']) for row in value['receivers'] for edge in row['inputs']}
        if not ports & owned:continue
        if not owned <= ports:
            raise CharacterRegistryError('重新连接动捕必须覆盖该原生 pairBlend 的全部原接收端口')
        selected.append(value['node']['path']+'.'+ATTRIBUTE)
    if remove:
        host._require_transaction()
        for plug in selected:
            c.setAttr(plug,lock=False)
            c.deleteAttr(plug)
    return tuple(selected)
