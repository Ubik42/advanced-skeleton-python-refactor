"""Explicit, undoable migration from legacy 0–1 to original 0–10 FKIK."""
from adv_py.core.character_registry import CharacterRegistryError


class UpgradeSourceSplineMode:
    def __init__(self, host):
        self.host = host

    def apply(self, systems=None):
        from adv_py.adapters.maya_source_spline_mode_upgrade import describe, install
        host = self.host
        before = host.read_character_registration()
        rows = describe(host, before, systems)
        if not rows:
            return before
        c = host._cmds
        frames = {float(c.currentTime(query=True))}
        for channel in before.channels:
            frames.update(float(frame) for frame in
                          (c.keyframe(channel.node + '.' + channel.attribute,
                                      query=True, timeChange=True) or ()))
        keyed = sorted(frames)
        frames.update((left + right) / 2. for left, right in zip(keyed, keyed[1:]))
        frames = tuple(sorted(frames))
        with host.transaction('Upgrade legacy source Spline FKIK 0-10'):
            if host.read_character_registration() != before or describe(host, before, systems) != rows:
                raise CharacterRegistryError('Spline 模式升级前场景发生变化')
            from adv_py.adapters.maya_source_parent_inverse import repair
            repair(host, before)
            poses = host.sample_character_animation(before, frames)
            after = install(host, before, rows)
            actual = host.sample_character_animation(after, frames)
            old_modes = {plan.mode_plug for plan, _ in rows}
            for (_, old), (_, new) in zip(poses, actual):
                if (tuple(name for name, _ in old.body_frames) !=
                        tuple(name for name, _ in new.body_frames)
                        or max(abs(left - right)
                            for (_, lefts), (_, rights) in zip(old.body_frames, new.body_frames)
                            for left, right in zip(lefts, rights)) > 1e-4):
                    raise CharacterRegistryError('Spline 模式升级改变身体动作，已回滚')
                if len(old.channels) != len(new.channels):
                    raise CharacterRegistryError('Spline 模式升级改变其他通道数量')
                for channel, (_, left), (_, right) in zip(before.channels, old.channels, new.channels):
                    factor = 10. if channel.node + '.' + channel.attribute in old_modes else 1.
                    if abs(left * factor - right) > 1e-6:
                        raise CharacterRegistryError('Spline 模式升级改变原通道值：' + channel.key)
            if host.read_character_registration() != after:
                raise CharacterRegistryError('Spline 模式升级登记读回不一致')
        return after
