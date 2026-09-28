"""Add Fit Part animator channels to the built character registry."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Mapping, Protocol

from adv_py.core.character_registry import (
    CharacterNode, CharacterRegistration, encode_registration,
)
from adv_py.core.fit_part import FitPartFinalPaths
from adv_py.core.fit_part_registration import (
    plan_fit_part_animation_channels,
)
from adv_py.core.fit_part_twist import FitPartTwistStep
from adv_py.core.fit_part_scale import FitPartScalePlan


class FitPartRegistrationHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def read_character_registration(self) -> CharacterRegistration: ...

    def capture_character_registration_node(
        self, path: str,
    ) -> CharacterNode: ...

    def write_character_registration_extension(
        self, before: CharacterRegistration,
        after: CharacterRegistration,
    ) -> None: ...


class RegisterFitPartChannels:
    def __init__(self, host: FitPartRegistrationHost) -> None:
        self._host = host

    def apply(
        self, before: CharacterRegistration,
        steps: tuple[FitPartTwistStep, ...],
        paths: FitPartFinalPaths,
        scale: FitPartScalePlan | None = None,
        ik_control_paths: Mapping[str, str] | None = None,
    ) -> CharacterRegistration:
        added = plan_fit_part_animation_channels(
            steps, paths, scale, ik_control_paths)
        if not added:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Fit Part 登记前角色文档已变化")
        keys = {channel.key for channel in before.channels}
        plugs = {(channel.node, channel.attribute)
                 for channel in before.channels}
        nodes = list(before.nodes)
        known = {node.path for node in nodes}
        for channel in added:
            if channel.key in keys or (channel.node, channel.attribute) in plugs:
                raise ValueError("Fit Part 登记通道冲突：" + channel.key)
            keys.add(channel.key)
            plugs.add((channel.node, channel.attribute))
            missing = []
            parent = channel.node
            while parent and parent not in known:
                missing.append(parent)
                parent = parent.rsplit("|", 1)[0]
            for path in reversed(missing):
                nodes.append(self._host.capture_character_registration_node(
                    path))
                known.add(path)
        after = replace(before,
                        channels=before.channels + added,
                        nodes=tuple(nodes))
        encode_registration(after)
        with self._host.transaction("登记 Fit Part 动画通道"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Fit Part 动画通道登记读回不一致")
        return after
