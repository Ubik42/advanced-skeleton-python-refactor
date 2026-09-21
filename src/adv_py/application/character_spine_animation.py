"""Sampled spine mode conversion with unchanged full-body poses at sample times."""
from adv_py.core.character_animation import CharacterAnimation, character_sample_frames, validate_character_animation
from adv_py.core.character_registry import CharacterRegistryError
from .character_animation import verify_character_animation_write


class BakeBodyCharacterSpineMode:
    def __init__(self,host): self._host=host

    def execute(self,start,end,mode,step=1):
        if mode not in ('fk','ik'):
            raise CharacterRegistryError("脊柱动画目标模式必须为 fk 或 ik")
        frames=character_sample_frames(start,end,step)
        reg=self._host.read_character_registration()
        self._host.preflight_character_keyframe(reg)
        original=self._host.capture_character_key_state(reg)
        unit=self._host.character_time_unit()
        with self._host.transaction("Bake animated spine " + mode.upper()):
            if self._host.read_character_registration()!=reg or self._host.capture_character_key_state(reg)!=original:
                raise RuntimeError("脊柱动画提交前场景发生变化")
            samples=self._host.match_character_spine_samples(reg,frames,mode)
            if self._host.capture_character_key_state(reg)!=original or self._host.character_time_unit()!=unit:
                raise RuntimeError("脊柱匹配采样改变了原曲线、时间或帧率")
            result=CharacterAnimation(unit,samples)
            validate_character_animation(result,reg)
            self._host.write_character_animation(reg,result.samples)
            verify_character_animation_write(self._host,reg,result,original)
        return result
