"""Build Fit aimAt receivers and register FK aim weights."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.body_fit_aim_at import (
    BodyFitAimAtSpec, BodyFitAimAtState, plan_body_fit_aim_at,
)
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class FitAimAtHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_body_fit_aim_at(
        self, spec: BodyFitAimAtSpec,
    ) -> BodyFitAimAtState: ...
    def create_body_fit_aim_at(
        self, spec: BodyFitAimAtSpec, state: BodyFitAimAtState,
    ) -> None: ...
    def capture_body_fit_aim_at(
        self, spec: BodyFitAimAtSpec, state: BodyFitAimAtState,
    ) -> bool: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def write_character_registration_extension(
        self, before: CharacterRegistration, after: CharacterRegistration,
    ) -> None: ...


class BuildFitAimAt:
    def __init__(self, host: FitAimAtHost) -> None:
        self._host = host

    def apply(self, metadata, controls, body_joints):
        specs = plan_body_fit_aim_at(
            tuple(metadata), tuple(controls), tuple(body_joints))
        states = tuple(self._host.preflight_body_fit_aim_at(spec)
                       for spec in specs)
        if not specs:
            return specs
        with self._host.transaction("创建 Fit AimAt"):
            for spec, state in zip(specs, states):
                self._host.create_body_fit_aim_at(spec, state)
            if any(not self._host.capture_body_fit_aim_at(spec, state)
                   for spec, state in zip(specs, states)):
                raise RuntimeError("Fit AimAt 构建读回不一致")
        return specs


class RegisterFitAimAt:
    def __init__(self, host: FitAimAtHost) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              specs: tuple[BodyFitAimAtSpec, ...]
              ) -> CharacterRegistration:
        if not specs:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Fit AimAt 登记前角色文档已变化")
        keys = {item.key for item in before.channels}
        plugs = {(item.node, item.attribute) for item in before.channels}
        channels = []
        for spec in specs:
            leaf = spec.fk_control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            channel = CharacterChannel(
                "fk.aim_at." + leaf, spec.fk_control,
                "aimAt", 0.0, 10.0)
            if (channel.key in keys or
                    (channel.node, channel.attribute) in plugs):
                raise ValueError("Fit AimAt 动画通道冲突：" + channel.key)
            keys.add(channel.key)
            plugs.add((channel.node, channel.attribute))
            channels.append(channel)
        after = replace(before, channels=before.channels + tuple(channels))
        encode_registration(after)
        with self._host.transaction("登记 Fit AimAt"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Fit AimAt 动画通道登记不一致")
        return after
