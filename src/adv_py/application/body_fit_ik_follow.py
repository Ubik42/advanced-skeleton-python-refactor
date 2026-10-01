"""Build Fit ikFollow on limb IK ends and register its channel."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.body_fit_ik_follow import plan_body_fit_ik_follow
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)

from .body_fit_follow import FitFollowHost


class BuildFitIkFollow:
    def __init__(self, host: FitFollowHost) -> None:
        self._host = host

    def apply(self, metadata, arm_ik, leg_ik, body_joints, *,
              spine=None, spline=None, driver_body_sources=()):
        specs = plan_body_fit_ik_follow(
            tuple(metadata), tuple(arm_ik), tuple(leg_ik),
            tuple(body_joints), spine=spine, spline=spline,
            driver_body_sources=tuple(driver_body_sources))
        states = tuple(self._host.preflight_body_fit_follow(spec)
                       for spec in specs)
        if not specs:
            return specs
        with self._host.transaction("创建 Fit IK Follow"):
            for spec, state in zip(specs, states):
                self._host.create_body_fit_follow(spec, state)
            if any(not self._host.capture_body_fit_follow(spec, state)
                   for spec, state in zip(specs, states)):
                raise RuntimeError("Fit IK Follow 构建读回不一致")
        return specs


class RegisterFitIkFollow:
    def __init__(self, host: FitFollowHost) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration, specs
              ) -> CharacterRegistration:
        if not specs:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("IK Follow 登记前角色文档已变化")
        keys = {item.key for item in before.channels}
        plugs = {(item.node, item.attribute) for item in before.channels}
        channels = []
        for spec in specs:
            leaf = spec.fk_control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            channel = CharacterChannel(
                "ik.follow." + leaf, spec.fk_control,
                spec.control_attribute, 0.0, 10.0)
            if (channel.key in keys or
                    (channel.node, channel.attribute) in plugs):
                raise ValueError("IK Follow 动画通道冲突：" + channel.key)
            keys.add(channel.key)
            plugs.add((channel.node, channel.attribute))
            channels.append(channel)
        after = replace(before, channels=before.channels + tuple(channels))
        encode_registration(after)
        with self._host.transaction("登记 IK Follow"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("IK Follow 动画通道登记不一致")
        return after
