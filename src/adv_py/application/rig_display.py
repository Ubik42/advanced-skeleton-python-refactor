"""Apply one ADV Display action and verify its scoped scene effect."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.rig_display import (
    RigDisplayPlan, RigDisplayState, audit_rig_display, plan_rig_display,
)


class RigDisplayHost(Protocol):
    def capture_rig_display(self) -> RigDisplayState: ...
    def preflight_rig_display(self, plan: RigDisplayPlan) -> None: ...
    def apply_rig_display(self, plan: RigDisplayPlan) -> None: ...
    def transaction(self, label: str): ...


class SetRigDisplay:
    def __init__(self, host: RigDisplayHost) -> None:
        self._host = host

    def apply(self, operation: str, value: bool | float) -> RigDisplayState:
        plan = plan_rig_display(
            self._host.capture_rig_display(), operation, value)
        self._host.preflight_rig_display(plan)
        with self._host.transaction("切换 ADV Display"):
            if self._host.capture_rig_display() != plan.before:
                raise RuntimeError("Display 输入在执行前发生变化")
            self._host.apply_rig_display(plan)
            after = self._host.capture_rig_display()
            issues = audit_rig_display(plan, after)
            if issues:
                raise RuntimeError("；".join(issues))
        return after
