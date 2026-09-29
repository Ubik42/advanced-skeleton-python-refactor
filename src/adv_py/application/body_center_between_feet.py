"""Build Root center-between-feet behavior and register its channel."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.body_center_between_feet import (
    BodyCenterBetweenFeetSpec, BodyCenterBetweenFeetState,
    plan_body_center_between_feet,
)
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class CenterBetweenFeetHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_body_center_between_feet(
        self, spec: BodyCenterBetweenFeetSpec,
    ) -> BodyCenterBetweenFeetState: ...
    def create_body_center_between_feet(
        self, spec: BodyCenterBetweenFeetSpec,
        state: BodyCenterBetweenFeetState,
    ) -> None: ...
    def capture_body_center_between_feet(
        self, spec: BodyCenterBetweenFeetSpec,
        state: BodyCenterBetweenFeetState,
    ) -> bool: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def write_character_registration_extension(
        self, before: CharacterRegistration, after: CharacterRegistration,
    ) -> None: ...


class BuildCenterBetweenFeet:
    def __init__(self, host: CenterBetweenFeetHost) -> None:
        self._host = host

    def apply(self, metadata, root_x, leg_ik):
        spec = plan_body_center_between_feet(
            tuple(metadata), root_x, tuple(leg_ik))
        if spec is None:
            return None
        state = self._host.preflight_body_center_between_feet(spec)
        with self._host.transaction("创建 Root Center Between Feet"):
            self._host.create_body_center_between_feet(spec, state)
            if not self._host.capture_body_center_between_feet(spec, state):
                raise RuntimeError("Root Center Between Feet 构建读回不一致")
        return spec


class RegisterCenterBetweenFeet:
    def __init__(self, host: CenterBetweenFeetHost) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              spec: BodyCenterBetweenFeetSpec | None
              ) -> CharacterRegistration:
        if spec is None:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Root Center Between Feet 登记前角色文档已变化")
        channel = CharacterChannel(
            "root.center_between_feet", spec.root_control,
            "centerBetweenFeet", 0.0, 10.0)
        if (channel.key in {item.key for item in before.channels}
                or (channel.node, channel.attribute) in {
                    (item.node, item.attribute) for item in before.channels}):
            raise ValueError("Root Center Between Feet 动画通道冲突")
        after = replace(before, channels=before.channels + (channel,))
        encode_registration(after)
        with self._host.transaction("登记 Root Center Between Feet"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Root Center Between Feet 动画通道登记不一致")
        return after
