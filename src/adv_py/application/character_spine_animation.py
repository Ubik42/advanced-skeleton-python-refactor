"""Original source Spline switching and precise legacy pose transfer."""
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
        if reg.spine is None:
            raise CharacterRegistryError("当前躯干只有 FK，没有可切换的脊柱 IK")
        from adv_py.core.body_spline import BodySplinePlan
        if isinstance(reg.spine,BodySplinePlan) and reg.spine.source_curve_points:
            if step!=1:
                raise CharacterRegistryError('原版 Spline 区间切换按逐帧执行，采样步长请设为 1')
            from adv_py.core.source_spline_animation import resolve_source_spline
            with self._host.transaction('Switch source Spline range '+mode.upper()):
                if self._host.read_character_registration()!=reg:
                    raise CharacterRegistryError('Spline 区间切换前角色发生变化')
                reg=self._host.enable_source_spline_first_translation(reg)
                bindings=tuple(resolve_source_spline(reg,plan.system_name)
                               for plan in (reg.spine,*reg.additional_spines))
                for binding in bindings:
                    if not self._host.switch_source_character_spline(reg,binding,mode,
                            time_range=(float(start),float(end)+1.)):
                        raise CharacterRegistryError('来源 Spline 不在可切换的源模式：'+(binding.plan.system_name or '主 Spline'))
                samples=self._host.sample_character_animation(reg,frames)
            return CharacterAnimation(self._host.character_time_unit(),samples)
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


class MatchSourceBodySplineMode:
    """Public original Spline Align/Switch, independent of precise transfer."""
    def __init__(self,host):self._host=host

    def execute(self,mode,system=None,*,align_only=False,time_range=None):
        from adv_py.core.source_spline_animation import resolve_source_spline
        if mode not in ('fk','ik'):
            raise CharacterRegistryError('Spline 目标模式需要 fk / ik')
        registration=self._host.read_character_registration()
        with self._host.transaction('Align source Spline' if align_only else 'Switch source Spline'):
            if self._host.read_character_registration()!=registration:
                raise CharacterRegistryError('Spline 操作前角色发生变化')
            registration=self._host.enable_source_spline_first_translation(registration)
            binding=resolve_source_spline(registration,system)
            if align_only:
                self._host.align_source_character_spline(registration,binding,mode)
                return True
            return self._host.switch_source_character_spline(registration,binding,mode,time_range=time_range)
