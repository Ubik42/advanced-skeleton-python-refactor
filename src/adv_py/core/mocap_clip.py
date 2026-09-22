"""Strict transfer document between an isolated FBX reader and the current scene."""
from dataclasses import asdict,dataclass
from hashlib import sha256
import json
from math import isfinite

from .mocap_source import MOCAP_TRANSFORM_ATTRIBUTES,MocapSourceValidationError


MOCAP_CLIP_FORMAT='adv_py_mocap_clip'
MOCAP_CLIP_SCHEMA=2
MOCAP_CLIP_MAX_SAMPLES=2000


def mocap_verification_times(key_times,maximum=MOCAP_CLIP_MAX_SAMPLES):
    """Spread bounded world-pose checks across the entire keyed time range."""
    keyed=tuple(sorted(set(key_times)))
    if not keyed or maximum<2:
        raise MocapSourceValidationError('动捕验收需要关键帧和至少两个采样位置')
    if any(not isinstance(time,(int,float)) or isinstance(time,bool) or not isfinite(time) for time in keyed):
        raise MocapSourceValidationError('动捕关键帧时间必须有限')
    candidates=tuple(sorted(set(keyed)|{(left+right)/2 for left,right in zip(keyed,keyed[1:])}))
    if len(candidates)<=maximum:return candidates
    indices=tuple(round(index*(len(candidates)-1)/(maximum-1)) for index in range(maximum))
    return tuple(candidates[index] for index in indices)


@dataclass(frozen=True,slots=True)
class MocapClipChannel:
    attribute: str
    keys: tuple[tuple[float,float],...]
    in_tangents: tuple[str,...] = ()
    out_tangents: tuple[str,...] = ()
    in_angles: tuple[float,...] = ()
    out_angles: tuple[float,...] = ()
    in_weights: tuple[float,...] = ()
    out_weights: tuple[float,...] = ()
    weighted: bool = False
    pre_infinity: int = 0
    post_infinity: int = 0
    tangent_locks: tuple[bool,...] = ()
    weight_locks: tuple[bool,...] = ()
    breakdown_times: tuple[float,...] = ()


@dataclass(frozen=True,slots=True)
class MocapClipJoint:
    name: str
    parent_name: str | None
    translate: tuple[float,float,float]
    rotate: tuple[float,float,float]
    joint_orient: tuple[float,float,float]
    scale: tuple[float,float,float]
    rotate_order: int
    channels: tuple[MocapClipChannel,...]


@dataclass(frozen=True,slots=True)
class MocapClip:
    up_axis: str
    linear_unit: str
    time_unit: str
    joints: tuple[MocapClipJoint,...]
    samples: tuple[tuple[float,tuple[tuple[float,...],...]],...]


def validate_mocap_clip(clip):
    if not isinstance(clip,MocapClip) or clip.up_axis not in ('y','z') or not clip.linear_unit or not clip.time_unit:
        raise MocapSourceValidationError('动捕片段单位或轴信息无效')
    if not 1<=len(clip.joints)<=512:
        raise MocapSourceValidationError('动捕片段关节数量无效')
    names=set();animated=False
    for index,joint in enumerate(clip.joints):
        if (not joint.name or ':' in joint.name or '|' in joint.name or joint.name in names
                or (index==0 and joint.parent_name is not None)
                or (index>0 and joint.parent_name not in names)
                or type(joint.rotate_order) is not int or not 0<=joint.rotate_order<=5):
            raise MocapSourceValidationError('动捕片段关节名称、父级或旋转顺序无效')
        names.add(joint.name)
        for values in (joint.translate,joint.rotate,joint.joint_orient,joint.scale):
            if len(values)!=3 or any(not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value) for value in values):
                raise MocapSourceValidationError('动捕片段关节静态变换无效')
        if min(joint.scale)<=0:
            raise MocapSourceValidationError('动捕片段包含非正缩放')
        attrs=set()
        for channel in joint.channels:
            if channel.attribute not in MOCAP_TRANSFORM_ATTRIBUTES or channel.attribute in attrs or not channel.keys:
                raise MocapSourceValidationError('动捕片段动画通道无效')
            attrs.add(channel.attribute);animated=True
            times=[]
            for time,value in channel.keys:
                if any(not isinstance(x,(int,float)) or isinstance(x,bool) or not isfinite(x) for x in (time,value)):
                    raise MocapSourceValidationError('动捕片段包含非有限关键帧')
                times.append(time)
            if any(left>=right for left,right in zip(times,times[1:])):
                raise MocapSourceValidationError('动捕片段关键帧时间不递增')
            tangents=(channel.in_tangents,channel.out_tangents,channel.in_angles,
                      channel.out_angles,channel.in_weights,channel.out_weights,
                      channel.tangent_locks,channel.weight_locks)
            if any(tangents) and any(len(values)!=len(channel.keys) for values in tangents):
                raise MocapSourceValidationError('动捕片段曲线切线数量不完整')
            if (not isinstance(channel.weighted,bool)
                    or type(channel.pre_infinity) is not int or type(channel.post_infinity) is not int
                    or any(not isinstance(value,str) or not value for values in tangents[:2] for value in values)
                    or any(not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value)
                           for values in tangents[2:6] for value in values)
                    or any(type(value) is not bool for values in tangents[6:] for value in values)
                    or (not channel.weighted and any(channel.weight_locks))
                    or any(not isinstance(time,(int,float)) or isinstance(time,bool) or not isfinite(time)
                           for time in channel.breakdown_times)
                    or any(time not in times for time in channel.breakdown_times)
                    or len(set(channel.breakdown_times))!=len(channel.breakdown_times)):
                raise MocapSourceValidationError('动捕片段曲线切线或循环设置无效')
    if not animated:raise MocapSourceValidationError('动捕片段没有动画通道')
    if not 1<=len(clip.samples)<=MOCAP_CLIP_MAX_SAMPLES:
        raise MocapSourceValidationError('动捕片段姿态采样数量无效')
    sample_times=[]
    for time,matrices in clip.samples:
        if (not isinstance(time,(int,float)) or isinstance(time,bool) or not isfinite(time)
                or len(matrices)!=len(clip.joints)):
            raise MocapSourceValidationError('动捕片段姿态采样时间或关节数量无效')
        sample_times.append(time)
        if any(len(matrix)!=16 or any(not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value)
                                      for value in matrix) for matrix in matrices):
            raise MocapSourceValidationError('动捕片段世界矩阵采样无效')
    if any(left>=right for left,right in zip(sample_times,sample_times[1:])):
        raise MocapSourceValidationError('动捕片段姿态采样时间不递增')
    return clip


def encode_mocap_clip(clip):
    validate_mocap_clip(clip)
    payload=dict(format=MOCAP_CLIP_FORMAT,schema_version=MOCAP_CLIP_SCHEMA,**asdict(clip))
    digest=sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()
    return json.dumps(dict(payload,content_sha256=digest),ensure_ascii=False,sort_keys=True,separators=(',',':'))


def decode_mocap_clip(text):
    try:raw=json.loads(text)
    except (TypeError,ValueError) as exc:raise MocapSourceValidationError('动捕片段 JSON 无效') from exc
    if not isinstance(raw,dict) or set(raw)!={'format','schema_version','up_axis','linear_unit','time_unit','joints','samples','content_sha256'}:
        raise MocapSourceValidationError('动捕片段字段集合无效')
    if raw['format']!=MOCAP_CLIP_FORMAT or type(raw['schema_version']) is not int or raw['schema_version'] not in (1,MOCAP_CLIP_SCHEMA):
        raise MocapSourceValidationError('动捕片段格式或版本无效')
    if not isinstance(raw['joints'],list):raise MocapSourceValidationError('动捕片段关节必须是数组')
    joints=[]
    for row in raw['joints']:
        if not isinstance(row,dict) or set(row)!={'name','parent_name','translate','rotate','joint_orient','scale','rotate_order','channels'}:
            raise MocapSourceValidationError('动捕片段关节字段无效')
        if not isinstance(row['channels'],list):raise MocapSourceValidationError('动捕片段通道必须是数组')
        channels=[]
        for channel in row['channels']:
            fields={'attribute','keys','in_tangents','out_tangents','in_angles','out_angles',
                    'in_weights','out_weights','weighted','pre_infinity','post_infinity'}
            if raw['schema_version']==2:
                fields.update(('tangent_locks','weight_locks','breakdown_times'))
            if not isinstance(channel,dict) or set(channel)!=fields or not isinstance(channel['keys'],list):
                raise MocapSourceValidationError('动捕片段通道字段无效')
            try:
                if any(not isinstance(key,list) or len(key)!=2 for key in channel['keys']):
                    raise ValueError('key shape')
                tangent_fields=('in_tangents','out_tangents','in_angles','out_angles','in_weights','out_weights')
                if raw['schema_version']==2:
                    tangent_fields+=('tangent_locks','weight_locks','breakdown_times')
                if any(not isinstance(channel[field],list) for field in tangent_fields):
                    raise ValueError('tangent shape')
                channels.append(MocapClipChannel(channel['attribute'],tuple(tuple(key) for key in channel['keys']),
                             *(tuple(channel[field]) for field in tangent_fields[:6]),channel['weighted'],
                             channel['pre_infinity'],channel['post_infinity'],
                             *(tuple(channel[field]) for field in tangent_fields[6:])))
            except (TypeError,ValueError) as exc:
                raise MocapSourceValidationError('动捕片段关键帧或曲线切线结构无效') from exc
        try:
            joints.append(MocapClipJoint(row['name'],row['parent_name'],tuple(row['translate']),tuple(row['rotate']),
                                         tuple(row['joint_orient']),tuple(row['scale']),row['rotate_order'],tuple(channels)))
        except TypeError as exc:
            raise MocapSourceValidationError('动捕片段关节变换结构无效') from exc
    if not isinstance(raw['samples'],list):raise MocapSourceValidationError('动捕片段采样必须是数组')
    try:
        if any(not isinstance(sample,list) or len(sample)!=2 or not isinstance(sample[1],list)
               or any(not isinstance(matrix,list) for matrix in sample[1]) for sample in raw['samples']):
            raise ValueError('sample shape')
        samples=tuple((time,tuple(tuple(matrix) for matrix in matrices)) for time,matrices in raw['samples'])
    except (TypeError,ValueError) as exc:
        raise MocapSourceValidationError('动捕片段姿态采样结构无效') from exc
    clip=validate_mocap_clip(MocapClip(raw['up_axis'],raw['linear_unit'],raw['time_unit'],tuple(joints),samples))
    payload={key:value for key,value in raw.items() if key!='content_sha256'}
    computed=sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()
    if computed!=raw['content_sha256']:
        raise MocapSourceValidationError('动捕片段内容摘要不匹配')
    return clip
