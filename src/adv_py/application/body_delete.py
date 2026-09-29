"""Remove an AdvancedSkeleton Body build while keeping its Fit source."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_delete import BodyDeletePlan


class BodyDeleteHost(Protocol):
    def plan_delete_body_advanced(self) -> BodyDeletePlan | None: ...
    def delete_body_advanced(self, plan: BodyDeletePlan) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class DeleteBodyAdvanced:
    def __init__(self, host: BodyDeleteHost) -> None:
        self._host = host

    def apply(self) -> bool:
        plan = self._host.plan_delete_body_advanced()
        if plan is None:
            return False
        if plan.group is None:
            return False
        with self._host.transaction("删除 Body AdvancedSkeleton，保留 Fit"):
            self._host.delete_body_advanced(plan)
        return True
