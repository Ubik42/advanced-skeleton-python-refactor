"""Sampled full-character animation, independent of scene paths and DCC APIs."""
from dataclasses import dataclass
import re

from .character_pose import CharacterPose, encode_character_pose, decode_character_pose, validate_character_pose
from .character_registry import CharacterRegistryError, canonical, digest, exact, finite, safe_json

ANIMATION_FORMAT = "adv_py_character_animation"
ANIMATION_MAX_BYTES = 64_000_000
ANIMATION_MAX_SAMPLES = 2000


@dataclass(frozen=True)
class CharacterAnimation:
    time_unit: str
    samples: tuple[tuple[float, CharacterPose], ...]


def character_sample_frames(start, end, step=1):
    if any(type(v) is not int for v in (start, end, step)) or step <= 0 or end < start:
        raise CharacterRegistryError("采样范围要求整数帧、正步长和递增区间")
    if (end-start) % step or (end-start)//step+1 > ANIMATION_MAX_SAMPLES:
        raise CharacterRegistryError("结束帧必须落在步长上，采样数最多 2000")
    return tuple(float(v) for v in range(start, end+1, step))


def decode_character_animation(text):
    doc=exact(safe_json(text,max_bytes=ANIMATION_MAX_BYTES),("format","version","payload","digest"))
    if doc["format"] != ANIMATION_FORMAT or type(doc["version"]) is not int or doc["version"] != 1:
        raise CharacterRegistryError("不支持的角色动画版本")
    raw=exact(doc["payload"],("time_unit","samples"))
    if digest(raw)!=doc["digest"]:
        raise CharacterRegistryError("角色动画摘要不匹配")
    unit=raw["time_unit"]
    if not isinstance(unit,str) or not re.fullmatch(r"(?:game|film|pal|ntsc|show|palf|ntscf|[0-9]+(?:\.[0-9]+)?fps)",unit):
        raise CharacterRegistryError("动画时间单位无效")
    if unit.endswith("fps") and finite(float(unit[:-3]))<=0:
        raise CharacterRegistryError("动画帧率必须为正数")
    rows=raw["samples"]
    if not isinstance(rows,list) or not 1<=len(rows)<=ANIMATION_MAX_SAMPLES:
        raise CharacterRegistryError("动画采样数必须在 1–2000 之间")
    samples=[]
    for row in rows:
        if not isinstance(row,list) or len(row)!=2:
            raise CharacterRegistryError("动画采样字段无效")
        frame=finite(row[0]); pose=decode_character_pose(canonical(row[1]))
        if samples:
            first=samples[0][1]
            if frame<=samples[-1][0]:
                raise CharacterRegistryError("动画采样时间必须严格递增")
            if (pose.compatibility!=first.compatibility or pose.spaces!=first.spaces
                    or any(tuple(k for k,_ in getattr(pose,f))!=tuple(k for k,_ in getattr(first,f))
                           for f in ("channels","space_frames","body_frames"))):
                raise CharacterRegistryError("动画片段的角色布局或空间来源不一致")
        samples.append((frame,pose))
    return CharacterAnimation(unit,tuple(samples))


def encode_character_animation(animation):
    payload={"time_unit":animation.time_unit,"samples":[[finite(t),safe_json(encode_character_pose(p))] for t,p in animation.samples]}
    text=canonical({"format":ANIMATION_FORMAT,"version":1,"payload":payload,"digest":digest(payload)})
    decode_character_animation(text)
    return text


def validate_character_animation(animation,registration):
    decode_character_animation(encode_character_animation(animation))
    for _,pose in animation.samples:
        validate_character_pose(pose,registration)
