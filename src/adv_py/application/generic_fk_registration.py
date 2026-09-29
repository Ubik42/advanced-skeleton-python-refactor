"""Add generic Fit FK controls to the character's animation registry."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.body_generic_fk import BodyGenericFkPlan
from adv_py.core.body_fk_channel_locks import BodyFkChannelLockSpec
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class RegisterGenericFk:
    def __init__(self, host) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              plan: BodyGenericFkPlan,
              locks: tuple[BodyFkChannelLockSpec, ...] = (),
              ) -> CharacterRegistration:
        if not plan.controls:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("通用 FK 登记前角色文档已变化")
        keys = {item.key for item in before.channels}
        plugs = {(item.node, item.attribute) for item in before.channels}
        channels = []
        nodes = list(before.nodes)
        known = {node.path for node in nodes}
        locked = {item.control: frozenset(item.attributes)
                  for item in locks}
        if (len(locked) != len(locks)
                or not set(locked) <= {
                    item.control_path for item in plan.controls}):
            raise ValueError("通用 FK 控制器锁定计划无效")
        for control in plan.controls:
            stem = control.control_name.removeprefix("AdvPy_")
            entries = [("", control.control_path,
                        tuple("rotate" + axis for axis in "XYZ")
                        + tuple("scale" + axis for axis in "XYZ"))]
            for suffix, path in ((".sub", control.sub_control_path),
                                 (".extra", control.extra_path)):
                if path is not None:
                    entries.append((suffix, path,
                                    tuple(kind + axis for kind in
                                          ("translate", "rotate", "scale")
                                          for axis in "XYZ")))
            for suffix, path, attrs in entries:
                for attr in attrs:
                    if attr in locked.get(path, ()):
                        continue
                    channel = CharacterChannel(
                        "generic.fk." + stem + suffix + "." + attr,
                        path, attr)
                    if (channel.key in keys or
                            (channel.node, channel.attribute) in plugs):
                        raise ValueError("通用 FK 动画通道冲突：" + channel.key)
                    keys.add(channel.key)
                    plugs.add((channel.node, channel.attribute))
                    channels.append(channel)
            for path in (plan.root_path, control.offset_path,
                         control.aim_path,
                         control.extra_path, control.control_path,
                         control.sub_control_path,
                         control.source_override_path):
                if path is None:
                    continue
                missing = []
                parent = path
                while parent and parent not in known:
                    missing.append(parent)
                    parent = parent.rsplit("|", 1)[0]
                for item in reversed(missing):
                    nodes.append(
                        self._host.capture_character_registration_node(item))
                    known.add(item)
        after = replace(before, channels=before.channels + tuple(channels),
                        nodes=tuple(nodes))
        encode_registration(after)
        with self._host.transaction("登记通用 Fit FK"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("通用 FK 登记读回不一致")
        return after
