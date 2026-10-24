"""Original Poser scalar commands and object popup actions, MEL 12024/12248."""
import shlex
from dataclasses import dataclass
from .maya_original_control_identity import source_control_from_role


def pose_rows(text):
    for statement in text.split(';'):
        if not statement.strip():
            continue
        tokens = shlex.split(statement)
        if len(tokens) != 2 or '.' not in tokens[0]:
            raise ValueError('原版 Poser 姿态指令格式无效：' + statement)
        yield tokens[0], float(tokens[1])


@dataclass(frozen=True)
class PoserKeyCommand:
    address: str
    command: str
    flags: tuple[tuple[str, object], ...]


def key_rows(text):
    """Decode asKeyAttrs' stored native key commands without evaluating MEL."""
    aliases = {'-t': 'time', '-time': 'time', '-v': 'value', '-value': 'value',
               '-itt': 'inTangentType', '-inTangentType': 'inTangentType',
               '-ott': 'outTangentType', '-outTangentType': 'outTangentType',
               '-at': 'attribute', '-attribute': 'attribute',
               '-f': 'float', '-float': 'float',
               '-bd': 'breakdown', '-breakdown': 'breakdown',
               '-wt': 'weightedTangents', '-weightedTangents': 'weightedTangents',
               '-iw': 'inWeight', '-inWeight': 'inWeight',
               '-ow': 'outWeight', '-outWeight': 'outWeight',
               '-ia': 'inAngle', '-inAngle': 'inAngle',
               '-oa': 'outAngle', '-outAngle': 'outAngle',
               '-l': 'lock', '-lock': 'lock', '-wl': 'weightLock', '-weightLock': 'weightLock'}
    booleans = {'breakdown', 'weightedTangents', 'lock', 'weightLock'}
    strings = {'inTangentType', 'outTangentType', 'attribute'}
    for statement in text.split(';'):
        if not statement.strip():
            continue
        tokens = shlex.split(statement)
        if len(tokens) < 2 or '.' not in tokens[0] or tokens[1] not in ('setKeyframe', 'keyTangent'):
            raise ValueError('原版 Poser 关键帧指令格式无效：' + statement)
        flags = []
        remaining = tokens[2:]
        if len(remaining) % 2:
            raise ValueError('原版 Poser 关键帧参数缺少值：' + statement)
        for name, value in zip(remaining[::2], remaining[1::2]):
            if name not in aliases:
                raise ValueError('未识别的原版 Poser 关键帧参数：' + name)
            key = aliases[name]
            if key in booleans:
                if value not in ('true', 'false', '0', '1', 'on', 'off'):
                    raise ValueError('原版 Poser 布尔参数无效：' + value)
                value = value in ('true', '1', 'on')
            elif key not in strings:
                value = tuple(float(part) for part in value.split(':')) if ':' in value else float(value)
            flags.append((key, value))
        yield PoserKeyCommand(tokens[0], tokens[1], tuple(flags))


class MayaOriginalPoserCommandsMixin:
    def key_original_poser_attributes(self, text, *, modifiers=None):
        """asKeyAttrs, MEL 12168: consecutive-channel first-value offset."""
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        modifier = raw.getModifiers() if modifiers is None else modifiers
        current_time = float(c.currentTime(query=True))
        rows = tuple(key_rows(text))
        targets = tuple(source_control_from_role(self, row.address.split('.', 1)[0])
                        + '.' + row.address.split('.', 1)[1] for row in rows)
        from .maya_native_animation_bake_boundary import capture, finish
        boundary = capture(self, tuple(self.scene_address(node) for node in dict.fromkeys(
            target.split('.', 1)[0] for target in targets if c.objExists(target))))
        missing = []
        previous = None
        first_value = None
        self._transaction_changed = True
        for row, target in zip(rows, targets):
            if target != previous:
                first_value = None
            previous = target
            if not c.objExists(target):
                missing.append(self.scene_address(target))
                continue
            flags = dict(row.flags)
            # The source offsets -t only, retaining its native range semantics.
            if 'time' in flags and modifier & (4 | 8):
                value = flags['time']
                flags['time'] = tuple(t + current_time for t in value) if isinstance(value, tuple) else value + current_time
            if 'value' in flags and modifier & 4:
                value = flags['value']
                current = float(c.getAttr(target))
                if first_value is None:
                    first_value = value
                flags['value'] = value + current - first_value
            getattr(c, row.command)(target, **flags)
        finish(self, boundary, mark_baked=False)
        if missing:
            c.warning('The following attributes can not be keyed:' + ','.join(missing) + ',')
        return targets

    def set_original_poser_attributes(self, text, *, modifiers=None):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        modifier = raw.getModifiers() if modifiers is None else modifiers
        missing = []
        self._transaction_changed = True
        for address, value in pose_rows(text):
            node, attribute = address.split('.', 1)
            if modifier & (4 | 8) and node.endswith('Main'):
                continue
            target = source_control_from_role(self, node) + '.' + attribute
            if c.objExists(target):
                try:
                    c.setAttr(target, value)
                except RuntimeError:
                    # The original catch leaves locked/connected channels alone.
                    pass
            else:
                missing.append(self.scene_address(target))
        if missing:
            c.warning('The following attributes can not be set:' + ','.join(missing) + ',')
        return tuple(missing)

    def original_poser_objects(self, text, action):
        self._require_transaction()
        if action not in ('select', 'key', 'linear_key'):
            raise ValueError('原版 Poser 对象操作无效：' + action)
        c = self._cmds
        missing = []
        targets = []
        self._transaction_changed = True
        if action == 'select':
            c.select(clear=True)
        for address, _ in pose_rows(text):
            node, attribute = address.split('.', 1)
            target = source_control_from_role(self, node)
            if action != 'select':
                target += '.' + attribute
            if c.objExists(target):
                targets.append(target)
            else:
                missing.append(self.scene_address(target))
        if action == 'select':
            for target in targets:
                c.select(target, add=True)
        else:
            from .maya_native_animation_bake_boundary import capture, finish
            boundary = capture(self, tuple(self.scene_address(node) for node in dict.fromkeys(target.split('.', 1)[0] for target in targets)))
            flags = dict(inTangentType='linear', outTangentType='linear') if action == 'linear_key' else {}
            for target in targets:
                c.setKeyframe(target, **flags)
            finish(self, boundary, mark_baked=False)
        if missing:
            c.warning('The following objects can not be found:' + ','.join(missing) + ',')
        return tuple(targets)
