"""Build Fit surface attachments and register their FK blend channels."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.body_fit_geo_attach import (
    BodyFitGeoAttachSpec, BodyFitGeoAttachState,
    plan_body_fit_geo_attach,
)
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class FitGeoAttachHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_body_fit_geo_attach(
        self, spec: BodyFitGeoAttachSpec,
    ) -> BodyFitGeoAttachState: ...
    def create_body_fit_geo_attach(
        self, spec: BodyFitGeoAttachSpec, state: BodyFitGeoAttachState,
    ) -> None: ...
    def capture_body_fit_geo_attach(
        self, spec: BodyFitGeoAttachSpec, state: BodyFitGeoAttachState,
    ) -> bool: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def write_character_registration_extension(
        self, before: CharacterRegistration, after: CharacterRegistration,
    ) -> None: ...


class BuildFitGeoAttach:
    def __init__(self, host: FitGeoAttachHost) -> None:
        self._host = host

    def apply(self, metadata, controls, body_joints, *, instances=(), source_native=False):
        specs = plan_body_fit_geo_attach(
            tuple(metadata), tuple(controls), tuple(body_joints), instances=instances, source_native=source_native)
        states = tuple(self._host.preflight_body_fit_geo_attach(spec)
                       for spec in specs)
        if not specs:
            return specs
        with self._host.transaction("创建 Fit Geo Attach"):
            for spec, state in zip(specs, states):
                self._host.create_body_fit_geo_attach(spec, state)
            if any(not self._host.capture_body_fit_geo_attach(spec, state)
                   for spec, state in zip(specs, states)):
                raise RuntimeError("Fit Geo Attach 构建读回不一致")
        return specs


class RegisterFitGeoAttach:
    def __init__(self, host: FitGeoAttachHost) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              specs: tuple[BodyFitGeoAttachSpec, ...]
              ) -> CharacterRegistration:
        if not specs:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Fit Geo Attach 登记前角色文档已变化")
        keys = {item.key for item in before.channels}
        plugs = {(item.node, item.attribute) for item in before.channels}
        channels = []
        for spec in specs:
            leaf = spec.fk_control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            channel = CharacterChannel(
                "fk.geo_attach." + leaf, spec.fk_control,
                "attach", 0.0, 10.0)
            if (channel.key in keys or
                    (channel.node, channel.attribute) in plugs):
                raise ValueError("Fit Geo Attach 动画通道冲突：" + channel.key)
            keys.add(channel.key)
            plugs.add((channel.node, channel.attribute))
            channels.append(channel)
        after = replace(before, channels=before.channels + tuple(channels))
        encode_registration(after)
        with self._host.transaction("登记 Fit Geo Attach"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Fit Geo Attach 动画通道登记不一致")
        return after
