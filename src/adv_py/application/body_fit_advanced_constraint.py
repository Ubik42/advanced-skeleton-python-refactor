"""Build and register Fit-driven FK constraint channels."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.body_fit_advanced_constraint import (
    BodyFitAdvancedConstraintSpec, plan_body_fit_advanced_constraints,
)
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class FitAdvancedConstraintHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def preflight_body_fit_advanced_constraint(
        self, spec: BodyFitAdvancedConstraintSpec,
    ) -> None: ...
    def create_body_fit_advanced_constraint(
        self, spec: BodyFitAdvancedConstraintSpec,
    ) -> None: ...
    def capture_body_fit_advanced_constraint(
        self, spec: BodyFitAdvancedConstraintSpec,
    ) -> bool: ...
    def read_character_registration(self) -> CharacterRegistration: ...
    def write_character_registration_extension(
        self, before: CharacterRegistration, after: CharacterRegistration,
    ) -> None: ...


class BuildFitAdvancedConstraints:
    def __init__(self, host: FitAdvancedConstraintHost) -> None:
        self._host = host

    def plan(self, metadata, controls, body_joints):
        specs = plan_body_fit_advanced_constraints(
            tuple(metadata), tuple(controls), tuple(body_joints))
        for spec in specs:
            self._host.preflight_body_fit_advanced_constraint(spec)
        return specs

    def apply(self, metadata, controls, body_joints):
        specs = self.plan(metadata, controls, body_joints)
        if not specs:
            return specs
        with self._host.transaction("创建 Fit Advanced Constraint"):
            for spec in specs:
                self._host.create_body_fit_advanced_constraint(spec)
            if any(not self._host.capture_body_fit_advanced_constraint(spec)
                   for spec in specs):
                raise RuntimeError("Fit Advanced Constraint 构建读回不一致")
        return specs


class RegisterFitAdvancedConstraints:
    def __init__(self, host: FitAdvancedConstraintHost) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              specs: tuple[BodyFitAdvancedConstraintSpec, ...]
              ) -> CharacterRegistration:
        if not specs:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Advanced Constraint 登记前角色文档已变化")
        channels = []
        existing_keys = {item.key for item in before.channels}
        existing_plugs = {(item.node, item.attribute)
                          for item in before.channels}
        for spec in specs:
            leaf = spec.fk_control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            channel = CharacterChannel(
                "fk.constraint." + leaf + "." + spec.kind,
                spec.fk_control, spec.attribute, 0.0, 10.0)
            if (channel.key in existing_keys
                    or (channel.node, channel.attribute) in existing_plugs):
                raise ValueError("Advanced Constraint 动画通道冲突："
                                 + channel.key)
            existing_keys.add(channel.key)
            existing_plugs.add((channel.node, channel.attribute))
            channels.append(channel)
        after = replace(before, channels=before.channels + tuple(channels))
        encode_registration(after)
        with self._host.transaction("登记 Fit Advanced Constraint"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Advanced Constraint 动画通道登记不一致")
        return after
