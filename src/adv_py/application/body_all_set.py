"""Populate AllSet once the complete Body graph has been constructed."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_all_set import (
    BodyAllSetNode, BodyAllSetPlan, plan_body_all_set,
)


class BodyAllSetHost(Protocol):
    def capture_body_scene_nodes(self) -> tuple[BodyAllSetNode, ...]: ...
    def capture_body_proximity_pin_sources(self) -> tuple[str, ...]: ...
    def name_body_unit_conversions(self, plan: BodyAllSetPlan) -> None: ...
    def populate_body_all_set(self, plan: BodyAllSetPlan) -> None: ...
    def capture_body_all_set_members(self) -> tuple[str, ...]: ...
    def capture_body_control_history(self, plan: BodyAllSetPlan) -> tuple[str, ...]: ...
    def disable_body_control_history(self, nodes: tuple[str, ...]) -> None: ...
    def read_body_control_history(self, nodes: tuple[str, ...]) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class PopulateBodyAllSet:
    def __init__(self, host: BodyAllSetHost) -> None:
        self._host = host

    def apply(
        self, before: tuple[BodyAllSetNode, ...], fit_container: str,
    ) -> BodyAllSetPlan:
        with self._host.transaction("登记角色 AllSet 节点"):
            plan = plan_body_all_set(
                before, self._host.capture_body_scene_nodes(), fit_container,
                self._host.capture_body_proximity_pin_sources())
            self._host.name_body_unit_conversions(plan)
            plan = plan_body_all_set(
                before, self._host.capture_body_scene_nodes(), fit_container,
                self._host.capture_body_proximity_pin_sources())
            self._host.populate_body_all_set(plan)
            actual = self._host.capture_body_all_set_members()
            if set(actual) != set(plan.members) or len(actual) != len(plan.members):
                raise RuntimeError("角色 AllSet 成员写后回读不一致")
            history = self._host.capture_body_control_history(plan)
            self._host.disable_body_control_history(history)
            if self._host.read_body_control_history(history):
                raise RuntimeError("角色控制器历史节点标记写后回读不一致")
        return plan
