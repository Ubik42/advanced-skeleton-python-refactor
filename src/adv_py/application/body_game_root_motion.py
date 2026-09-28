"""Transaction for the standalone Game Engine Root Motion command."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_game_root_motion import (
    GameRootMotionInput, GameRootMotionPlan, GameRootMotionState,
    audit_game_root_motion, plan_game_root_motion,
)


class GameRootMotionHost(Protocol):
    def capture_game_root_motion_input(self) -> GameRootMotionInput: ...
    def preflight_game_root_motion(self, plan: GameRootMotionPlan) -> None: ...
    def apply_game_root_motion(self, plan: GameRootMotionPlan) -> None: ...
    def capture_game_root_motion(self, plan: GameRootMotionPlan
                                 ) -> GameRootMotionState: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class SwitchGameRootMotion:
    def __init__(self, host: GameRootMotionHost) -> None:
        self._host = host

    def apply(self, *, create: bool) -> GameRootMotionPlan:
        plan = plan_game_root_motion(
            self._host.capture_game_root_motion_input(), create=create)
        self._host.preflight_game_root_motion(plan)
        with self._host.transaction(
                "创建 Game Engine Root Motion" if create
                else "删除 Game Engine Root Motion"):
            if self._host.capture_game_root_motion_input() != plan.source:
                raise RuntimeError("Root Motion 执行前角色状态已变化")
            self._host.apply_game_root_motion(plan)
            issues = audit_game_root_motion(
                plan, self._host.capture_game_root_motion(plan))
            if issues:
                raise RuntimeError("；".join(issues))
        return plan
