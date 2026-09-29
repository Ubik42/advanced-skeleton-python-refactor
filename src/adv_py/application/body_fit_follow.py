"""Attach Fit Follow graphs and register their animation channels."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.body_fit_follow import (
    BodyFitFollowSourceState, BodyFitFollowSpec, plan_body_fit_follow,
)
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class FitFollowHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_body_fit_follow(
        self, spec: BodyFitFollowSpec,
    ) -> BodyFitFollowSourceState: ...
    def create_body_fit_follow(
        self, spec: BodyFitFollowSpec, source: BodyFitFollowSourceState,
    ) -> None: ...
    def capture_body_fit_follow(
        self, spec: BodyFitFollowSpec, source: BodyFitFollowSourceState,
    ) -> bool: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def write_character_registration_extension(
        self, before: CharacterRegistration, after: CharacterRegistration,
    ) -> None: ...


class BuildFitFollow:
    def __init__(self, host: FitFollowHost) -> None:
        self._host = host

    def apply(self, metadata, controls, body_joints):
        specs = plan_body_fit_follow(
            tuple(metadata), tuple(controls), tuple(body_joints))
        states = tuple(self._host.preflight_body_fit_follow(spec)
                       for spec in specs)
        if not specs:
            return specs
        with self._host.transaction("创建 Fit Follow"):
            for spec, state in zip(specs, states):
                self._host.create_body_fit_follow(spec, state)
            if any(not self._host.capture_body_fit_follow(spec, state)
                   for spec, state in zip(specs, states)):
                raise RuntimeError("Fit Follow 构建读回不一致")
        return specs


class RegisterFitFollow:
    def __init__(self, host: FitFollowHost) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              specs: tuple[BodyFitFollowSpec, ...]
              ) -> CharacterRegistration:
        if not specs:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Fit Follow 登记前角色文档已变化")
        channels = []
        existing_keys = {item.key for item in before.channels}
        existing_plugs = {(item.node, item.attribute)
                          for item in before.channels}
        for spec in specs:
            leaf = spec.fk_control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            for attr in ("follow",) + (
                    ("followLeftRight",) if spec.opposite_target else ()) + (
                    ("followWorld",) if spec.world_target else ()):
                channel = CharacterChannel(
                    "fk.follow." + leaf + "." + attr,
                    spec.fk_control, attr, 0.0, 10.0)
                if (channel.key in existing_keys or
                        (channel.node, channel.attribute) in existing_plugs):
                    raise ValueError("Fit Follow 动画通道冲突："
                                     + channel.key)
                existing_keys.add(channel.key)
                existing_plugs.add((channel.node, channel.attribute))
                channels.append(channel)
        after = replace(before, channels=before.channels + tuple(channels))
        encode_registration(after)
        with self._host.transaction("登记 Fit Follow"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Fit Follow 动画通道登记不一致")
        return after
