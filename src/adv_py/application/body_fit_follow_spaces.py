"""Build Fit followSpaces levels and register FK animation channels."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.body_fit_follow_spaces import (
    BodyFitFollowSpacesSpec, BodyFitFollowSpacesState,
    plan_body_fit_follow_spaces,
)
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class FitFollowSpacesHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_body_fit_follow_spaces(
        self, spec: BodyFitFollowSpacesSpec,
    ) -> BodyFitFollowSpacesState: ...
    def create_body_fit_follow_spaces(
        self, spec: BodyFitFollowSpacesSpec,
        state: BodyFitFollowSpacesState,
    ) -> None: ...
    def capture_body_fit_follow_spaces(
        self, spec: BodyFitFollowSpacesSpec,
        state: BodyFitFollowSpacesState,
    ) -> bool: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def write_character_registration_extension(
        self, before: CharacterRegistration, after: CharacterRegistration,
    ) -> None: ...


class BuildFitFollowSpaces:
    def __init__(self, host: FitFollowSpacesHost) -> None:
        self._host = host

    def apply(self, metadata, controls, body_joints, *, main_path, root_path,
              main_extra_paths=()):
        specs = plan_body_fit_follow_spaces(
            tuple(metadata), tuple(controls), tuple(body_joints),
            main_path=main_path, root_path=root_path,
            main_extra_paths=tuple(main_extra_paths))
        states = tuple(self._host.preflight_body_fit_follow_spaces(spec)
                       for spec in specs)
        if not specs:
            return specs
        with self._host.transaction("创建 Fit Follow Spaces"):
            for spec, state in zip(specs, states):
                self._host.create_body_fit_follow_spaces(spec, state)
            if any(not self._host.capture_body_fit_follow_spaces(spec, state)
                   for spec, state in zip(specs, states)):
                raise RuntimeError("Fit Follow Spaces 构建读回不一致")
        return specs


class RegisterFitFollowSpaces:
    def __init__(self, host: FitFollowSpacesHost) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              specs: tuple[BodyFitFollowSpacesSpec, ...]
              ) -> CharacterRegistration:
        if not specs:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Follow Spaces 登记前角色文档已变化")
        channels = []
        keys = {item.key for item in before.channels}
        plugs = {(item.node, item.attribute) for item in before.channels}
        for spec in specs:
            leaf = spec.fk_control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            for target in spec.targets:
                channel = CharacterChannel(
                    "fk.follow_space." + leaf + "." + target.label,
                    spec.fk_control, "follow" + target.label, 0.0, 10.0)
                if (channel.key in keys or
                        (channel.node, channel.attribute) in plugs):
                    raise ValueError("Follow Spaces 动画通道冲突："
                                     + channel.key)
                keys.add(channel.key)
                plugs.add((channel.node, channel.attribute))
                channels.append(channel)
        after = replace(before, channels=before.channels + tuple(channels))
        encode_registration(after)
        with self._host.transaction("登记 Fit Follow Spaces"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Follow Spaces 动画通道登记不一致")
        return after
