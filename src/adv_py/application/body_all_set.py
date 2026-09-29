"""Populate AllSet once the complete Body graph has been constructed."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_all_set import (
    BodyAllSetNode, BodyAllSetPlan, plan_body_all_set,
)


class BodyAllSetHost(Protocol):
    def capture_body_scene_nodes(self) -> tuple[BodyAllSetNode, ...]: ...
    def populate_body_all_set(self, plan: BodyAllSetPlan) -> None: ...
    def capture_body_all_set_members(self) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class PopulateBodyAllSet:
    def __init__(self, host: BodyAllSetHost) -> None:
        self._host = host

    def apply(
        self, before: tuple[BodyAllSetNode, ...], fit_container: str,
    ) -> BodyAllSetPlan:
        plan = plan_body_all_set(
            before, self._host.capture_body_scene_nodes(), fit_container)
        with self._host.transaction("登记角色 AllSet 节点"):
            self._host.populate_body_all_set(plan)
            actual = self._host.capture_body_all_set_members()
            if set(actual) != set(plan.members) or len(actual) != len(plan.members):
                raise RuntimeError("角色 AllSet 成员写后回读不一致")
        return plan
