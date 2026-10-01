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
        if not isinstance(limb,str) or not limb or mode not in ('fk','ik'):
            raise CharacterRegistryError("四肢转换需要有效 IK 系统名称与 fk / ik")
        side=FitBuildSide(side)
        frames=character_sample_frames(start,end,step)
        reg=self._host.read_character_registration()
        if reg.source_limbs:
            from adv_py.core.source_limb_animation import resolve_source_limb
            source_binding=resolve_source_limb(reg,limb,side.value)
        else:
            if limb not in ('arm','leg') or side is FitBuildSide.MIDDLE:
                raise CharacterRegistryError('当前标准角色需要 arm / leg 和 R / L')
            required={f'{limb}.fkLength.{side.value}.{index}' for index in (0,1)}
            required.update(f'{limb}.ikOrientation.{side.value}.{segment}.rotate{axis}'
                            for segment in ('upper','lower') for axis in 'XYZ')
            if not required.issubset({ch.key for ch in reg.channels}):
                raise CharacterRegistryError("先显式启用四肢动画骨段登记")
        self._host.preflight_character_keyframe(reg)
        keys=self._host.capture_character_key_state(reg)
        unit=self._host.character_time_unit()
        helpers=self._host.sample_character_limb_helpers(reg,frames,limb,side.value)
        guard=None
        if reg.source_limbs:
            guard_frame=float(frames[0])-1.
            guard_pose=self._host.sample_character_animation(reg,(guard_frame,))[0][1]
            guard=(guard_frame,dict(guard_pose.channels)[source_binding.blend_key])
        with self._host.transaction(f"Bake animated {limb} {side.value} {mode}"):
            if self._host.read_character_registration()!=reg or self._host.capture_character_key_state(reg)!=keys:
                raise RuntimeError("四肢动画提交前场景发生变化")
            samples=self._host.match_character_limb_samples(reg,frames,limb,side,mode)
            if self._host.capture_character_key_state(reg)!=keys or self._host.character_time_unit()!=unit:
                raise RuntimeError("四肢匹配采样改变了原曲线、时间或帧率")
            animation=CharacterAnimation(unit,samples)
            validate_character_animation(animation,reg)
            if reg.source_limbs:
                self._host.write_source_character_limb_animation(reg,samples,source_binding,guard)
                _verify_source_limb_animation(self._host,reg,animation,keys,source_binding,guard)
            else:
                self._host.write_character_animation(reg,samples)
                verify_character_animation_write(self._host,reg,animation,keys)
            actual_helpers=self._host.sample_character_limb_helpers(reg,frames,limb,side.value)
            if (tuple((f,tuple(p for p,_ in rows)) for f,rows in helpers)!=tuple((f,tuple(p for p,_ in rows)) for f,rows in actual_helpers)
                    or any(control_space_pose_error(left,right)>1e-4 for (_,left),(_,right) in zip(helpers,actual_helpers))):
                raise RuntimeError('四肢动画转换改变了变形 helper 的世界姿态')
        return animation


def _verify_source_limb_animation(host,registration,animation,previous,binding,guard=None):
    from adv_py.core.character_pose import character_pose_error,POSE_TOLERANCE
    actual=host.sample_character_animation(registration,tuple(frame for frame,_ in animation.samples))
    if (tuple(frame for frame,_ in actual)!=tuple(frame for frame,_ in animation.samples)
            or any(character_pose_error(left,right)>POSE_TOLERANCE for (_,left),(_,right)
                   in zip(animation.samples,actual))):
        raise CharacterRegistryError('来源 RP 动画写入后姿态不一致')
    current=host.capture_character_key_state(registration)
    if current[0]!=previous[0] or tuple(row[0] for row in current[1])!=tuple(row[0] for row in previous[1]):
        raise CharacterRegistryError('来源 RP 动画写入改变时间或通道结构')
    owned=binding.animation_keys(registration)
    for index,(before,after) in enumerate(zip(previous[1],current[1])):
        if before[0] not in owned:
            if before!=after:
                raise CharacterRegistryError('来源 RP 动画改写其他系统曲线：'+before[0])
            continue
        old=dict(zip(before[2],before[3]))
        new=dict(zip(after[2],after[3]))
        desired={frame:pose.channels[index][1] for frame,pose in animation.samples}
        if guard is not None and before[0]==binding.blend_key:
            desired[guard[0]]=guard[1]
        if (any(frame not in new or abs(new[frame]-value)>1e-6 for frame,value in desired.items())
                or any(frame not in desired and new.get(frame)!=value for frame,value in old.items())):
            raise CharacterRegistryError('来源 RP 动画键值变化或覆盖区间外关键帧：'+before[0])
    host.read_character_registration()


class MatchSourceBodyLimbMode:
    """Single-pose asAlignFKIK/asSwitchFKIK on the final registered RP graph."""
    def __init__(self,host): self._host=host

    def execute(self,limb,side,mode):
        from adv_py.core.source_limb_animation import resolve_source_limb
        if mode not in ('fk','ik'):
            raise CharacterRegistryError('来源 RP 目标模式需要 fk / ik')
        registration=self._host.read_character_registration()
        binding=resolve_source_limb(registration,limb,FitBuildSide(side).value)
        self._host.preflight_character_pose(registration)
        before=self._host.capture_character_pose(registration)
        with self._host.transaction('Switch source RP '+binding.label+' '+binding.side):
            if (self._host.read_character_registration()!=registration or
                    self._host.capture_character_pose(registration)!=before):
                raise CharacterRegistryError('来源 RP 切换前角色或姿态发生变化')
            self._host.apply_source_character_limb_mode(registration,binding,mode)
            after=self._host.capture_character_pose(registration)
            error=max(abs(a-b) for (_,left),(_,right) in zip(before.body_frames,after.body_frames)
                      for a,b in zip(left,right))
            if error>1e-4:
                raise CharacterRegistryError('来源 RP 切换改变身体姿态，已回滚：'+str(error))
        return after
