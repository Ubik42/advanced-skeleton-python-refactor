"""Scoped Optimize operation for a character's skin clusters."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.skin_optimize import (
    SkinInfluenceState, SkinOptimizePlan, audit_removed_influences,
    plan_remove_unused_influences,
)


class SkinOptimizeHost(Protocol):
    def capture_skin_influences(self) -> tuple[SkinInfluenceState, ...]: ...
    def preflight_skin_optimize(self, plan: SkinOptimizePlan) -> None: ...
    def remove_unused_skin_influences(self, plan: SkinOptimizePlan) -> None: ...
    def transaction(self, label: str): ...


class RemoveUnusedSkinInfluences:
    def __init__(self, host: SkinOptimizeHost) -> None:
        self._host = host

    def apply(self) -> tuple[int, int]:
        plan = plan_remove_unused_influences(
            self._host.capture_skin_influences())
        self._host.preflight_skin_optimize(plan)
        with self._host.transaction("清理无效 Skin 影响关节"):
            if self._host.capture_skin_influences() != plan.before:
                raise RuntimeError("Skin 输入在执行前发生变化")
            self._host.remove_unused_skin_influences(plan)
            issues = audit_removed_influences(
                plan, self._host.capture_skin_influences())
            if issues:
                raise RuntimeError("；".join(issues))
        return len(plan.before), sum(item.unused_count for item in plan.before)
