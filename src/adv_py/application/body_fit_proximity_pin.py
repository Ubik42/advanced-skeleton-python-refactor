"""Build Fit proximity pins and register FK pin weights."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.body_fit_proximity_pin import (
    BodyFitProximityPinSpec, BodyFitProximityPinState,
    plan_body_fit_proximity_pin,
)
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class FitProximityPinHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_body_fit_proximity_pin(
        self, spec: BodyFitProximityPinSpec,
    ) -> BodyFitProximityPinState: ...
    def create_body_fit_proximity_pin(
        self, spec: BodyFitProximityPinSpec,
        state: BodyFitProximityPinState,
    ) -> None: ...
    def capture_body_fit_proximity_pin(
        self, spec: BodyFitProximityPinSpec,
        state: BodyFitProximityPinState,
    ) -> bool: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def write_character_registration_extension(
        self, before: CharacterRegistration, after: CharacterRegistration,
    ) -> None: ...


class BuildFitProximityPin:
    def __init__(self, host: FitProximityPinHost) -> None:
        self._host = host

    def apply(self, metadata, controls, body_joints, *, instances=(), source_native=False):
        specs = plan_body_fit_proximity_pin(
            tuple(metadata), tuple(controls), tuple(body_joints), instances=instances, source_native=source_native)
        states = tuple(self._host.preflight_body_fit_proximity_pin(spec)
                       for spec in specs)
        if not specs:
            return specs
        with self._host.transaction("创建 Fit Proximity Pin"):
            for spec, state in zip(specs, states):
                self._host.create_body_fit_proximity_pin(spec, state)
            if any(not self._host.capture_body_fit_proximity_pin(spec, state)
                   for spec, state in zip(specs, states)):
                raise RuntimeError("Fit Proximity Pin 构建读回不一致")
        return specs


class RegisterFitProximityPin:
    def __init__(self, host: FitProximityPinHost) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              specs: tuple[BodyFitProximityPinSpec, ...]
              ) -> CharacterRegistration:
        if not specs:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Fit Proximity Pin 登记前角色文档已变化")
        keys = {item.key for item in before.channels}
        plugs = {(item.node, item.attribute) for item in before.channels}
        channels = []
        for spec in specs:
            leaf = spec.fk_control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            channel = CharacterChannel(
                "fk.proximity_pin." + leaf, spec.fk_control,
                "pin", 0.0, 10.0)
            if (channel.key in keys or
                    (channel.node, channel.attribute) in plugs):
                raise ValueError("Fit Proximity Pin 动画通道冲突：" + channel.key)
            keys.add(channel.key)
            plugs.add((channel.node, channel.attribute))
            channels.append(channel)
        after = replace(before, channels=before.channels + tuple(channels))
        encode_registration(after)
        with self._host.transaction("登记 Fit Proximity Pin"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Fit Proximity Pin 动画通道登记不一致")
        return after
