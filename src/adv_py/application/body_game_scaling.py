"""Scene boundary for the independent Game Engine Scaling command."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_game_scaling import (
    GameScalingJointState, GameScalingPlan, audit_body_game_scaling,
    plan_body_game_scaling,
)


class BodyGameScalingHost(Protocol):
    def capture_game_scaling_joints(self) -> tuple[GameScalingJointState, ...]: ...
    def preflight_game_scaling(self, plan: GameScalingPlan) -> None: ...
    def apply_game_scaling(self, plan: GameScalingPlan) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class SwitchBodyGameScaling:
    def __init__(self, host: BodyGameScalingHost) -> None:
        self._host = host

    def plan(self, *, enable: bool) -> GameScalingPlan:
        plan = plan_body_game_scaling(
            self._host.capture_game_scaling_joints(), enable=enable)
        self._host.preflight_game_scaling(plan)
        return plan

    def apply(self, *, enable: bool) -> GameScalingPlan:
        before = self._host.capture_game_scaling_joints()
        plan = plan_body_game_scaling(before, enable=enable)
        self._host.preflight_game_scaling(plan)
        with self._host.transaction("切换 Game Engine Scaling"):
            self._host.apply_game_scaling(plan)
            issues = audit_body_game_scaling(
                plan, before, self._host.capture_game_scaling_joints())
            if issues:
                raise RuntimeError("Game Engine Scaling 写后状态不符："
                                   + "；".join(issues))
        return plan
