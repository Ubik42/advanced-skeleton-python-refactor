"""Strict transfer document between an isolated FBX reader and the current scene."""
from dataclasses import asdict,dataclass
from hashlib import sha256
import json
from math import isfinite

from .mocap_source import MOCAP_TRANSFORM_ATTRIBUTES,MocapSourceValidationError


MOCAP_CLIP_FORMAT='adv_py_mocap_clip'
MOCAP_CLIP_SCHEMA=1


@dataclass(frozen=True,slots=True)
class MocapClipChannel:
    attribute: str
    keys: tuple[tuple[float,float],...]


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
    if not animated:raise MocapSourceValidationError('动捕片段没有动画通道')
    if not 1<=len(clip.samples)<=2000:
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
    if raw['format']!=MOCAP_CLIP_FORMAT or type(raw['schema_version']) is not int or raw['schema_version']!=MOCAP_CLIP_SCHEMA:
        raise MocapSourceValidationError('动捕片段格式或版本无效')
    if not isinstance(raw['joints'],list):raise MocapSourceValidationError('动捕片段关节必须是数组')
    joints=[]
    for row in raw['joints']:
        if not isinstance(row,dict) or set(row)!={'name','parent_name','translate','rotate','joint_orient','scale','rotate_order','channels'}:
            raise MocapSourceValidationError('动捕片段关节字段无效')
        if not isinstance(row['channels'],list):raise MocapSourceValidationError('动捕片段通道必须是数组')
        channels=[]
        for channel in row['channels']:
            if not isinstance(channel,dict) or set(channel)!={'attribute','keys'} or not isinstance(channel['keys'],list):
                raise MocapSourceValidationError('动捕片段通道字段无效')
            channels.append(MocapClipChannel(channel['attribute'],tuple(tuple(key) for key in channel['keys'])))
        joints.append(MocapClipJoint(row['name'],row['parent_name'],tuple(row['translate']),tuple(row['rotate']),
                                     tuple(row['joint_orient']),tuple(row['scale']),row['rotate_order'],tuple(channels)))
    if not isinstance(raw['samples'],list):raise MocapSourceValidationError('动捕片段采样必须是数组')
    samples=tuple((time,tuple(tuple(matrix) for matrix in matrices)) for time,matrices in raw['samples'])
    clip=validate_mocap_clip(MocapClip(raw['up_axis'],raw['linear_unit'],raw['time_unit'],tuple(joints),samples))
    if json.loads(encode_mocap_clip(clip))['content_sha256']!=raw['content_sha256']:
        raise MocapSourceValidationError('动捕片段内容摘要不匹配')
    return clip
