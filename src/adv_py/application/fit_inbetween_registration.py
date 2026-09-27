"""Register Inbetween controls in the existing character document."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.character_registry import (
    CharacterChannel, CharacterNode, CharacterRegistration,
    encode_registration,
)

from .fit_inbetween_limb_segment import InbetweenLimbSegmentResult


class InbetweenRegistrationHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def read_character_registration(self) -> CharacterRegistration: ...

    def capture_inbetween_registration_node(
        self, path: str
    ) -> CharacterNode: ...

    def write_character_registration_extension(
        self, before: CharacterRegistration,
        after: CharacterRegistration,
    ) -> None: ...


class RegisterInbetweenControls:
    def __init__(self, host: InbetweenRegistrationHost) -> None:
        self._host = host

    def apply(
        self, before: CharacterRegistration,
        segments: tuple[InbetweenLimbSegmentResult, ...],
    ) -> CharacterRegistration:
        if not segments:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Inbetween 登记前角色文档已变化")
        channels = list(before.channels)
        nodes = list(before.nodes)
        keys = {channel.key for channel in channels}
        plugs = {(channel.node, channel.attribute)
                 for channel in channels}
        known = {node.path for node in nodes}

        def add_node_chain(path: str) -> None:
            missing = []
            while path and path not in known:
                missing.append(path)
                path = path.rsplit("|", 1)[0]
            for node_path in reversed(missing):
                nodes.append(self._host.capture_inbetween_registration_node(
                    node_path))
                known.add(node_path)

        def add(key: str, path: str, attribute: str) -> None:
            if key in keys or (path, attribute) in plugs:
                raise ValueError("Inbetween 登记通道冲突：" + key)
            channel = CharacterChannel(key, path, attribute)
            channels.append(channel)
            keys.add(key)
            plugs.add((path, attribute))
            add_node_chain(path)

        for segment in segments:
            parts = segment.fk.parts
            if parts is None:
                raise ValueError("Inbetween 控制器登记缺少 FK Part")
            start = segment.fk.anchor.start_body_name
            control = segment.fk.anchor.fk_control_path
            add(f"inbetween.{start}.bias", control, "bias")
            add(f"inbetween.{start}.visibility", control,
                "inbetweenVis")
            for part in parts.parts:
                path = (parts.fk_system_path + "|" + part.offset_name
                        + "|" + part.extra_name + "|"
                        + part.control_name)
                for axis in "XYZ":
                    add(f"inbetween.{part.part_name}.rotate{axis}",
                        path, "rotate" + axis)
        after = replace(before, channels=tuple(channels),
                        nodes=tuple(nodes))
        encode_registration(after)
        with self._host.transaction("登记 Inbetween 控制器"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Inbetween 控制器登记读回不一致")
        return after
