"""Register Wheel / RollingBall animator inputs and owned DAG helpers."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.body_fit_wheel import BodyFitWheelSpec
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class RegisterFitWheels:
    def __init__(self, host) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              wheels: tuple[BodyFitWheelSpec, ...]
              ) -> CharacterRegistration:
        if not wheels:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Wheel 登记前角色文档已变化")
        keys = {item.key for item in before.channels}
        plugs = {(item.node, item.attribute) for item in before.channels}
        channels = []
        nodes = list(before.nodes)
        known = {node.path for node in nodes}
        system = "|Group|MotionSystem|WheelSystem"
        for wheel in wheels:
            spec = wheel.control
            stem = spec.control_name.removeprefix("AdvPy_")
            for attr in ("diameter", "autoRoll"):
                channel = CharacterChannel(
                    "fit.wheel." + stem + "." + attr,
                    spec.control_path, attr)
                if (channel.key in keys or
                        (channel.node, channel.attribute) in plugs):
                    raise ValueError("Wheel 动画通道冲突：" + channel.key)
                keys.add(channel.key)
                plugs.add((channel.node, channel.attribute))
                channels.append(channel)
            receiver = (spec.source_override_path or
                        (spec.sub_control_path or spec.control_path)
                        + "|AdvPy_WheelFKX" + stem)
            paths = (
                system,
                system + "|prevPosOffset" + stem,
                system + "|prevPosOffset" + stem + "|prevPos" + stem,
                system + "|prevPosOffset" + stem + "|prevPos" + stem
                + "|prevPosAngler" + stem,
                system + "|nowPos" + stem,
                spec.control_path + "|prevPosSteer" + stem,
                receiver,
            )
            for path in paths:
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
        with self._host.transaction("登记 Wheel / RollingBall"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Wheel 动画通道登记不一致")
        return after
