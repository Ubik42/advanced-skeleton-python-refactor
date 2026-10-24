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
    def apply_game_root_motion(self, plan: GameRootMotionPlan) -> GameRootMotionPlan | None: ...
    def capture_game_root_motion(self, plan: GameRootMotionPlan
                                 ) -> GameRootMotionState: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class SwitchGameRootMotion:
    def __init__(self, host: GameRootMotionHost) -> None:
        self._host = host

    def apply(self, *, create: bool) -> GameRootMotionPlan:
        capture, plan = self._prepare(create)
        with self._host.transaction(
                "创建 Game Engine Root Motion" if create
                else "删除 Game Engine Root Motion"):
            return self._apply_checked(capture, plan)

    def apply_in_transaction(self, *, create: bool) -> GameRootMotionPlan:
        """Run the same native operation inside an export/rebuild undo chunk.

        The scene host still enforces its active transaction. Export's native
        Root Motion prompt must not create a nested Maya undo transaction.
        """
        capture, plan = self._prepare(create)
        return self._apply_checked(capture, plan)

    def _prepare(self, create):
        capture = (getattr(self._host, "capture_game_root_motion_creation_input", None)
                   if create else None) or self._host.capture_game_root_motion_input
        plan = plan_game_root_motion(
            capture(), create=create)
        self._host.preflight_game_root_motion(plan)
        return capture, plan

    def _apply_checked(self, capture, plan):
        if capture() != plan.source:
            raise RuntimeError("Root Motion 执行前角色状态已变化")
        applied = self._host.apply_game_root_motion(plan)
        if applied is not None:
            plan = applied
        issues = audit_game_root_motion(
            plan, self._host.capture_game_root_motion(plan))
        if issues:
            raise RuntimeError("；".join(issues))
        return plan
