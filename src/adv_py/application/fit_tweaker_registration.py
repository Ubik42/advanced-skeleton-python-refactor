"""Register Tweaker controls with the built character."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.character_registry import (
    CharacterChannel, CharacterNode, CharacterRegistration,
    encode_registration,
)
from adv_py.core.fit_tweaker import FitTweakerPlan


class FitTweakerRegistrationHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def capture_character_registration_node(self, path: str) -> CharacterNode: ...
    def write_character_registration_extension(
        self, before: CharacterRegistration,
        after: CharacterRegistration,
    ) -> None: ...


class RegisterFitTweakers:
    def __init__(self, host: FitTweakerRegistrationHost) -> None:
        self._host = host

    def apply(
        self, before: CharacterRegistration, plan: FitTweakerPlan,
    ) -> CharacterRegistration:
        if not plan.controls:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Tweaker 登记前角色文档已变化")
        after = self.describe(before, plan)
        if after == before:
            return before
        with self._host.transaction("登记 Tweaker 动画通道"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Tweaker 动画通道登记读回不一致")
        return after

    def describe(
        self, before: CharacterRegistration, plan: FitTweakerPlan,
    ) -> CharacterRegistration:
        if not plan.controls:
            return before
        added = [CharacterChannel(
            "tweaker.visibility", plan.global_control_path,
            "tweakerVis", 0.0, 1.0)]
        for spec in plan.controls:
            leaf = spec.target_path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            for channel in ("translate", "rotate", "scale"):
                for axis in "XYZ":
                    attr = channel + axis
                    added.append(CharacterChannel(
                        "tweaker." + leaf + "." + attr,
                        spec.control_path, attr))
        keys = {channel.key for channel in before.channels}
        plugs = {(channel.node, channel.attribute)
                 for channel in before.channels}
        nodes = list(before.nodes)
        known = {node.path for node in nodes}
        for channel in added:
            if channel.key in keys or (channel.node, channel.attribute) in plugs:
                raise ValueError("Tweaker 动画通道冲突：" + channel.key)
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
                        channels=before.channels + tuple(added),
                        nodes=tuple(nodes))
        encode_registration(after)
        return after
