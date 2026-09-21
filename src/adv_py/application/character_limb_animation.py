"""Explicit FK-length and IK-orientation channels for complete limb matching."""
from dataclasses import dataclass

from adv_py.core.character_registry import CharacterRegistration
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.character_animation import CharacterAnimation, character_sample_frames, validate_character_animation
from adv_py.core.fit_symmetry import FitBuildSide
from .character_animation import verify_character_animation_write
from adv_py.core.body_control_spaces import control_space_pose_error


@dataclass(frozen=True)
class LimbAnimationUpgradePlan:
    before: CharacterRegistration
    after: CharacterRegistration


class EnableBodyCharacterLimbAnimation:
    def __init__(self,host): self._host=host

    def plan(self):
        before=self._host.read_character_registration()
        return LimbAnimationUpgradePlan(before,self._host.describe_character_limb_animation(before))

    def apply(self):
        plan=self.plan()
        if plan.before==plan.after:
            return plan.after
        with self._host.transaction("Enable complete limb animation channels"):
            if self._host.read_character_registration()!=plan.before:
                raise RuntimeError("四肢动画登记提交前角色发生变化")
            if self._host.describe_character_limb_animation(plan.before)!=plan.after:
                raise RuntimeError("四肢动画登记提交前骨段通道发生变化")
            self._host.extend_character_limb_registration(plan.before,plan.after)
            if self._host.read_character_registration()!=plan.after:
                raise RuntimeError("四肢动画登记读回不一致")
        return plan.after


class BakeBodyCharacterLimbMode:
    def __init__(self,host): self._host=host

    def execute(self,start,end,limb,side,mode,step=1):
        if limb not in ('arm','leg') or mode not in ('fk','ik'):
            raise CharacterRegistryError("四肢转换需要 arm / leg 与 fk / ik")
        side=FitBuildSide(side)
        if side not in (FitBuildSide.RIGHT,FitBuildSide.LEFT):
            raise CharacterRegistryError("四肢转换需要 R / L")
        frames=character_sample_frames(start,end,step)
        reg=self._host.read_character_registration()
        required={f'{part}.fkLength.{s}.{index}' for part in ('arm','leg') for s in ('R','L') for index in (0,1)}
        required.update(f'{part}.ikOrientation.{s}.{segment}.rotate{axis}' for part in ('arm','leg') for s in ('R','L') for segment in ('upper','lower') for axis in 'XYZ')
        if not required.issubset({ch.key for ch in reg.channels}):
            raise CharacterRegistryError("先显式启用四肢动画骨段登记")
        self._host.preflight_character_keyframe(reg)
        keys=self._host.capture_character_key_state(reg)
        unit=self._host.character_time_unit()
        helpers=self._host.sample_character_limb_helpers(reg,frames,limb,side.value)
        with self._host.transaction(f"Bake animated {limb} {side.value} {mode}"):
            if self._host.read_character_registration()!=reg or self._host.capture_character_key_state(reg)!=keys:
                raise RuntimeError("四肢动画提交前场景发生变化")
            samples=self._host.match_character_limb_samples(reg,frames,limb,side,mode)
            if self._host.capture_character_key_state(reg)!=keys or self._host.character_time_unit()!=unit:
                raise RuntimeError("四肢匹配采样改变了原曲线、时间或帧率")
            animation=CharacterAnimation(unit,samples)
            validate_character_animation(animation,reg)
            self._host.write_character_animation(reg,samples)
            verify_character_animation_write(self._host,reg,animation,keys)
            actual_helpers=self._host.sample_character_limb_helpers(reg,frames,limb,side.value)
            if (tuple((f,tuple(p for p,_ in rows)) for f,rows in helpers)!=tuple((f,tuple(p for p,_ in rows)) for f,rows in actual_helpers)
                    or any(control_space_pose_error(left,right)>1e-4 for (_,left),(_,right) in zip(helpers,actual_helpers))):
                raise RuntimeError('四肢动画转换改变了变形 helper 的世界姿态')
        return animation
