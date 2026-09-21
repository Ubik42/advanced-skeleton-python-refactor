"""Upgrade and switch registered control spaces in one undoable operation."""
from adv_py.core.character_spaces import has_animated_spaces, space_channels
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.body_control_spaces import control_space_pose_error, SPACE_TOLERANCE


class EnableBodyCharacterSpaceAnimation:
    def __init__(self, host):
        self._host = host

    def apply(self):
        host = self._host
        registration = host.read_character_registration()
        host.preflight_character_keyframe(registration)
        if has_animated_spaces(registration):
            return registration
        host.preflight_character_space_animation(registration)
        before = host.capture_control_space_pose(registration.spaces)
        with host.transaction('Enable character space animation'):
            if host.read_character_registration() != registration:
                raise RuntimeError('空间动画安装前登记变化')
            after = host.install_character_space_animation(registration)
            if (host.read_character_registration() != after or
                    control_space_pose_error(before, host.capture_control_space_pose(after.spaces)) > SPACE_TOLERANCE):
                raise RuntimeError('空间动画安装改变角色姿态')
        return after


class SwitchBodyCharacterSpace:
    def __init__(self, host):
        self._host = host

    def execute(self, key, mode, frame):
        if type(frame) is not int:
            raise CharacterRegistryError('空间切换时刻必须是整数帧')
        host = self._host
        registration = host.read_character_registration()
        if not has_animated_spaces(registration):
            raise CharacterRegistryError('先启用角色空间动画')
        registration.spaces.space(key).source(mode)
        host.preflight_character_keyframe(registration)
        keys = host.capture_character_key_state(registration)
        before = host.sample_character_animation(registration, (float(frame),))[0][1]
        if dict(before.spaces)[key] == mode:
            return before
        with host.transaction('Switch animated character space '+key):
            if host.read_character_registration()!=registration or host.capture_character_key_state(registration)!=keys:
                raise RuntimeError('空间切换提交前场景变化')
            expected = host.switch_character_space(registration,key,mode,frame)
            actual = host.sample_character_animation(registration,(float(frame),))[0][1]
            from adv_py.core.character_pose import character_pose_error
            if (character_pose_error(expected,actual)>SPACE_TOLERANCE or
                    control_space_pose_error(before.body_frames,actual.body_frames)>SPACE_TOLERANCE or
                    control_space_pose_error(before.space_frames,actual.space_frames)>SPACE_TOLERANCE or
                    dict(actual.spaces)[key]!=mode):
                raise RuntimeError('动画空间切换造成姿态跳变，已回滚')
            current=host.capture_character_key_state(registration)
            changed={ch.key for ch in space_channels(registration.spaces.space(key))
                     if ch.key.endswith('.mode') or f'.{mode}.' in ch.key}
            if current[0]!=keys[0] or tuple(row[0] for row in current[1])!=tuple(row[0] for row in keys[1]):
                raise RuntimeError('空间切换改变了时间或曲线结构')
            for old,new in zip(keys[1],current[1]):
                if old[0] not in changed and old!=new:
                    raise RuntimeError('空间切换改写了其他控制曲线')
                old_values=dict(zip(old[2],old[3]));new_values=dict(zip(new[2],new[3]))
                if any(t!=frame and new_values.get(t)!=v for t,v in old_values.items()):
                    raise RuntimeError('空间切换改写了已有事件键值')
            host.read_character_registration()
        return actual
