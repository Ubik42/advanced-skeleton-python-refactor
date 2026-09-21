"""Whole-clip transactions. Samples are explicit; existing off-sample keys survive."""
from dataclasses import dataclass
from pathlib import Path
import os
import tempfile

from adv_py.core.character_animation import (
    CharacterAnimation, ANIMATION_MAX_BYTES, character_sample_frames,
    encode_character_animation, decode_character_animation, validate_character_animation,
)
from adv_py.core.character_pose import CharacterPose, POSE_TOLERANCE, character_pose_error
from adv_py.core.character_registry import CharacterRegistration, CharacterRegistryError


@dataclass(frozen=True)
class CharacterAnimationPlan:
    registration: CharacterRegistration
    animation: CharacterAnimation
    key_state: tuple
    before: CharacterPose


class CaptureBodyCharacterAnimation:
    def __init__(self,host): self._host=host

    def execute(self,start,end,step=1):
        frames=character_sample_frames(start,end,step)
        reg=self._host.read_character_registration()
        self._host.preflight_character_keyframe(reg)
        keys=self._host.capture_character_key_state(reg)
        unit=self._host.character_time_unit()
        samples=self._host.sample_character_animation(reg,frames)
        if (self._host.read_character_registration()!=reg or self._host.capture_character_key_state(reg)!=keys
                or self._host.character_time_unit()!=unit):
            raise RuntimeError("动画采样期间场景发生变化")
        animation=CharacterAnimation(unit,samples)
        validate_character_animation(animation,reg)
        return animation


class ApplyBodyCharacterAnimation:
    def __init__(self,host): self._host=host

    def plan(self,animation):
        animation=decode_character_animation(encode_character_animation(animation))
        reg=self._host.read_character_registration()
        validate_character_animation(animation,reg)
        self._host.preflight_character_keyframe(reg)
        if animation.time_unit!=self._host.character_time_unit():
            raise CharacterRegistryError("动画与场景时间单位不一致；不隐式修改帧率")
        before=self._host.capture_character_pose(reg)
        from adv_py.core.character_spaces import has_animated_spaces
        if not has_animated_spaces(reg) and before.spaces!=animation.samples[0][1].spaces:
            raise CharacterRegistryError("动画写入要求相同的控制空间来源")
        return CharacterAnimationPlan(reg,animation,self._host.capture_character_key_state(reg),before)

    def apply(self,animation):
        plan=self.plan(animation)
        reg=plan.registration
        with self._host.transaction("Apply complete character animation"):
            if (self._host.read_character_registration()!=reg
                    or self._host.capture_character_key_state(reg)!=plan.key_state
                    or self._host.capture_character_pose(reg)!=plan.before
                    or self._host.character_time_unit()!=plan.animation.time_unit):
                raise RuntimeError("动画提交前场景发生变化")
            self._host.write_character_animation(reg,plan.animation.samples)
            verify_character_animation_write(self._host,reg,plan.animation,plan.key_state)
        return plan.animation


def save_character_animation(animation,destination):
    target=Path(destination).expanduser().absolute()
    text=encode_character_animation(animation)
    if target.exists(): raise FileExistsError(target)
    fd,temporary=tempfile.mkstemp(prefix=".character-animation-",suffix=".tmp",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as stream:
            stream.write(text+"\n");stream.flush();os.fsync(stream.fileno())
        if decode_character_animation(Path(temporary).read_text(encoding="utf-8"))!=animation:
            raise RuntimeError("动画临时文件复检失败")
        os.link(temporary,target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def load_character_animation(source):
    path=Path(source).expanduser()
    if path.stat().st_size>ANIMATION_MAX_BYTES: raise ValueError("动画文件过大")
    return decode_character_animation(path.read_text(encoding="utf-8"))


def verify_character_animation_write(host,reg,animation,original_keys):
    frames=tuple(t for t,_ in animation.samples)
    actual=host.sample_character_animation(reg,frames)
    if tuple(t for t,_ in actual)!=frames or any(character_pose_error(a,b)>POSE_TOLERANCE
            for (_,a),(_,b) in zip(animation.samples,actual)):
        raise RuntimeError("动画写入后的身体或空间姿态不匹配，已回滚")
    frame,rows=host.capture_character_key_state(reg)
    if frame!=original_keys[0] or tuple(r[0] for r in rows)!=tuple(c.key for c in reg.channels):
        raise RuntimeError("动画写入改变了当前时间或通道结构")
    for index,(old,new) in enumerate(zip(original_keys[1],rows)):
        previous=dict(zip(old[2],old[3])); current=dict(zip(new[2],new[3]))
        desired={t:p.channels[index][1] for t,p in animation.samples}
        if (any(t not in current or abs(current[t]-v)>1e-6 for t,v in desired.items())
                or any(t not in desired and current.get(t)!=v for t,v in previous.items())):
            raise RuntimeError("动画键值读回失败或改写了采样范围外的键")
    host.read_character_registration()
