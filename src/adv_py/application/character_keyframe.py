"""Current-frame whole-character keys with audited control spaces."""
from dataclasses import dataclass

from adv_py.core.character_pose import (
    CharacterPose, POSE_TOLERANCE, decode_character_pose, encode_character_pose,
    validate_character_pose, character_pose_error,
    normalize_character_pose_compatibility,
)
from adv_py.core.character_registry import CharacterRegistration, CharacterRegistryError


@dataclass(frozen=True)
class CharacterKeyPlan:
    registration: CharacterRegistration
    target: CharacterPose
    before: CharacterPose
    key_state: tuple


class CaptureAnimatedBodyCharacterPose:
    def __init__(self,host): self._host=host

    def execute(self):
        registration=self._host.read_character_registration()
        self._host.preflight_character_keyframe(registration)
        pose=self._host.capture_character_pose(registration)
        pose=normalize_character_pose_compatibility(pose,registration)
        return pose


class KeyBodyCharacterPose:
    def __init__(self,host): self._host=host

    def plan(self,pose):
        pose=decode_character_pose(encode_character_pose(pose))
        registration=self._host.read_character_registration()
        pose=normalize_character_pose_compatibility(pose,registration)
        self._host.preflight_character_keyframe(registration)
        before=self._host.capture_character_pose(registration)
        validate_character_pose(before,registration)
        from adv_py.core.character_spaces import has_animated_spaces
        if not has_animated_spaces(registration) and before.spaces!=pose.spaces:
            raise CharacterRegistryError("当前写键不改变空间来源；动画空间切换需独立流程")
        return CharacterKeyPlan(registration,pose,before,self._host.capture_character_key_state(registration))

    def apply(self,pose):
        plan=self.plan(pose)
        with self._host.transaction("Key complete character pose"):
            if (self._host.read_character_registration()!=plan.registration
                    or self._host.capture_character_key_state(plan.registration)!=plan.key_state
                    or self._host.capture_character_pose(plan.registration)!=plan.before):
                raise RuntimeError("全身写键前角色、时间或曲线发生变化")
            self._host.key_character_pose(plan.registration,plan.target)
            result=self._host.capture_character_pose(plan.registration)
            validate_character_pose(result,plan.registration)
            if character_pose_error(plan.target,result)>POSE_TOLERANCE:
                raise RuntimeError("全身写键姿态不一致；空间偏移必须兼容，已回滚")
            frame,rows=self._host.capture_character_key_state(plan.registration)
            if frame!=plan.key_state[0]: raise RuntimeError("写键改变了当前时间")
            if tuple(r[0] for r in rows)!=tuple(c.key for c in plan.registration.channels):
                raise RuntimeError("写键后的通道集合不完整")
            for original,current,(_,value) in zip(plan.key_state[1],rows,plan.target.channels):
                old=dict(zip(original[2],original[3]));new=dict(zip(current[2],current[3]))
                if frame not in new or abs(new[frame]-value)>1e-6 or any(t!=frame and new.get(t)!=v for t,v in old.items()):
                    raise RuntimeError("全身写键读回失败或改变了其他帧键值")
            self._host.read_character_registration()
        return result
