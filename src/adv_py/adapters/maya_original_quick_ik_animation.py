"""Observe native key/bake/static edits on an existing original QuickIK graph."""
from copy import deepcopy
from dataclasses import dataclass

from adv_py.core.character_registry import CharacterRegistryError, canonical
from adv_py.core.source_quick_ik import ATTRIBUTE,decode_quick_ik
from .maya_original_quick_ik_state import capture as capture_quick, _snapshot, _audit
from .maya_source_name_matcher_session import _commands, _node, _plug
from .maya_source_native_animation import _time_curve, _settings
from .maya_driving_registration import _write_string


@dataclass(frozen=True)
class QuickAnimationBoundary:
    records: tuple
    time_inputs: frozenset
    curve_ids: frozenset
    blend_values: tuple
    documents: tuple=()


def capture(host):
    c=_commands(host)
    records=tuple(deepcopy(value) for value in capture_quick(host))
    documents=tuple((value['group']['uuid'],deepcopy(value)) for value in records)
    time_inputs=set()
    values=[]
    for value in records:
        # Allowed keys on the temporary controls may have been added after
        # creation. Freeze their live edges as well before native deletion.
        value['nodes']=[_snapshot(c,row['path']) for row in value['nodes']]
        for row in value['nodes']:
            for edge in row['inputs']:
                if _time_curve(c,edge['source']):
                    time_inputs.add((row['uuid'],edge['destination'],edge['source_uuid']))
            if row['kind']=='pairBlend':
                names=tuple('in'+kind+axis+number for kind in ('Translate','Rotate')
                            for number in ('1','2') for axis in 'XYZ')
                names+=('weight','rotInterpolation','rotateMode','translateXMode','translateYMode','translateZMode')
                values.append((row['uuid'],tuple((name,c.getAttr(row['path']+'.'+name))
                    for name in names if c.objExists(row['path']+'.'+name))))
    curves=frozenset(_node(c,node)[1] for node in c.ls(type='animCurve') or ()) if records else frozenset()
    return QuickAnimationBoundary(records,frozenset(time_inputs),curves,tuple(values),documents)


def _axes(value,identity,ports):
    """Controller axes reached by this exact pairBlend's recorded output."""
    selected=set()
    retained=set()
    for row in value['receivers']:
        for edge in row['inputs']:
            if edge['source_uuid']!=identity:continue
            axis=('Translate' if edge['destination'].startswith('translate') else 'Rotate')+edge['destination'][-1]
            (selected if (row['uuid'],edge['destination']) in ports else retained).add(axis)
    # One output axis can fan out to several receivers. It is editable only
    # when all of its receivers participate in the native operation.
    return frozenset(selected-retained)


def _blend_inputs(value,identity,ports):
    axes=_axes(value,identity,ports)
    attributes={'in'+axis+number for axis in axes for number in ('1','2')}
    for family in ('Translate','Rotate'):
        if all(family+axis in axes for axis in 'XYZ'):
            attributes.update('in'+family+number for number in ('1','2'))
    receivers={(row['uuid'],edge['destination']) for row in value['receivers']
               for edge in row['inputs'] if edge['source_uuid']==identity}
    if receivers and receivers<=ports:
        attributes.add('weight')
    return frozenset(attributes)


def _curve_for_axis(row,identity,axis):
    return any(edge['source_uuid']==identity and edge['destination'] in ('in'+axis+'1','in'+axis+'2')
               for edge in row['inputs'])


def _constraint_for_axis(value,driver,source,axis):
    """A deleted pairBlend may expose its existing same-axis constraint."""
    if driver is None or driver['kind']!='pairBlend' or axis.startswith('Translate'):
        return False
    address,identity=source
    if identity not in value['constraints']:
        return False
    for edge in driver['inputs']:
        if edge['source_uuid']!=identity:
            continue
        if edge['destination'] in ('in'+axis+'1','in'+axis+'2') and edge['source']==address:
            return True
        if edge['destination'] in ('inRotate1','inRotate2'):
            if edge['source']+axis[-1]==address:
                return True
    return False


def finish(host,boundary,ports,*,static=False):
    """Refresh metadata only; all node creation/editing remains Maya's native job."""
    if not boundary.records:
        return
    host._require_transaction()
    c=_commands(host)
    values=dict(boundary.blend_values)
    documents=dict(boundary.documents)
    for original in boundary.records:
        value=deepcopy(original)
        group=value['group']
        plug=group['path']+'.'+ATTRIBUTE
        if (_node(c,group['path'])!=(group['path'],group['uuid'])
                or not c.getAttr(plug,lock=True)
                or decode_quick_ik(c.getAttr(plug))!=documents.get(group['uuid'],original)):
            raise CharacterRegistryError('原生动画操作期间 QuickIK 图记录变化或解锁')
        nodes={row['uuid']:row for row in value['nodes']}
        retained=[]
        removed=set()
        for row in value['nodes']:
            matches=c.ls(row['uuid'],long=True) or ()
            axes=_axes(value,row['uuid'],ports)
            blend_inputs=_blend_inputs(value,row['uuid'],ports) if row['kind']=='pairBlend' else frozenset()
            if not matches:
                if row['kind']!='pairBlend' or not axes or c.objExists(row['path']):
                    raise CharacterRegistryError('原生动画操作删除或替换了 QuickIK 非混合节点')
                if any((receiver['uuid'],edge['destination']) not in ports
                       for receiver in value['receivers'] for edge in receiver['inputs']
                       if edge['source_uuid']==row['uuid']):
                    raise CharacterRegistryError('原生动画操作删除了仍驱动未覆盖控制器的 QuickIK pairBlend')
                removed.add(row['uuid'])
                continue
            current=_snapshot(c,matches[0])
            if any(current[key]!=row[key] for key in ('path','uuid','kind','parent')):
                raise CharacterRegistryError('原生动画操作改变了 QuickIK 节点身份或父级')
            editable=row['kind'] in ('transform','joint') and row['path'].startswith(value['group']['path']+'|')
            for edge in current['inputs']:
                if edge in row['inputs']:
                    continue
                if static or not _time_curve(c,edge['source']):
                    raise CharacterRegistryError('原生动画操作给 QuickIK 增加了非允许输入')
                attribute=edge['destination']
                controlled=attribute in blend_inputs
                controlled|=editable and attribute in tuple(kind+axis for kind in ('translate','rotate','scale') for axis in 'XYZ')
                if not controlled:
                    raise CharacterRegistryError('原生动画操作改变了未覆盖的 QuickIK 端口')
                same_axis=tuple(attribute[:-1]+number for number in ('1','2')) \
                    if row['kind']=='pairBlend' and attribute[-1:] in ('1','2') else (attribute,)
                if edge['source_uuid'] in boundary.curve_ids and not any(
                        old['source_uuid']==edge['source_uuid'] and old['destination'] in same_axis for old in row['inputs']):
                    raise CharacterRegistryError('原生动画操作接管了其他既有 QuickIK 动画曲线')
            for old in row['inputs']:
                if old in current['inputs']:
                    continue
                timed=(row['uuid'],old['destination'],old['source_uuid']) in boundary.time_inputs
                controlled=old['destination'] in blend_inputs
                if not timed or not (controlled or editable):
                    raise CharacterRegistryError('原生动画操作删除了 QuickIK 原约束输入')
                if static and c.ls(old['source_uuid'],long=True):
                    raise CharacterRegistryError('静态清理断开了仍存活的 QuickIK 时间曲线')
            if row['kind']=='pairBlend':
                before=dict(values[row['uuid']])
                for setting in _settings(c,current['path']):
                    attribute=setting['attribute']
                    changed=setting['value']!=before[attribute]
                    controlled=attribute in blend_inputs
                    if changed and (static or not controlled):
                        raise CharacterRegistryError('原生动画操作改变了未覆盖的 QuickIK 缓存值')
            retained.append(current)
        receivers=[]
        for row in value['receivers']:
            if _node(c,row['path'])!=(row['path'],row['uuid']):
                raise CharacterRegistryError('原生动画操作替换了 QuickIK 接收控制器')
            inputs=[]
            for old in row['inputs']:
                source=c.connectionInfo(row['path']+'.'+old['destination'],sourceFromDestination=True)
                if source and _plug(c,source)==(old['source'],old['source_uuid']):
                    inputs.append(old)
                    continue
                if (row['uuid'],old['destination']) not in ports:
                    raise CharacterRegistryError('原生动画操作改接了未覆盖的 QuickIK 控制器')
                axis=('Translate' if old['destination'].startswith('translate') else 'Rotate')+old['destination'][-1]
                driver=nodes.get(old['source_uuid'])
                if source and not _time_curve(c,source):
                    actual=_plug(c,source)
                    if old['source_uuid'] not in removed or not _constraint_for_axis(value,driver,actual,axis):
                        raise CharacterRegistryError('原生动画操作为 QuickIK 接入非原约束驱动')
                    inputs.append(dict(destination=old['destination'],source=actual[0],source_uuid=actual[1]))
                    continue
                if source:
                    curve=_plug(c,source)[1]
                    if static or curve in boundary.curve_ids:
                        if not driver or driver['kind']!='pairBlend' or not _curve_for_axis(driver,curve,axis):
                            raise CharacterRegistryError('原生动画操作接管了其他原有控制器曲线')
                elif static and old['source_uuid'] not in removed:
                    raise CharacterRegistryError('静态清理断开了仍存活的 QuickIK 输出')
            receivers.append({**row,'inputs':inputs})
        value['nodes']=retained
        value['receivers']=receivers
        if value['version']==2:
            value['blend_settings']=[dict(uuid=row['uuid'],settings=_settings(c,row['path']))
                                     for row in retained if row['kind']=='pairBlend']
        plug=value['group']['path']+'.'+ATTRIBUTE
        _write_string(c,plug,canonical(value))
        c.setAttr(plug,lock=True)
        _audit(c,value)
