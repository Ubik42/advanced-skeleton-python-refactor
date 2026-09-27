"""Application boundary for ADV's Body Squash Controller."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.squash_controller import (
    SquashPlan, SquashSelection, plan_squash_controller,
)


class SquashControllerHost(Protocol):
    def capture_squash_selection(self) -> SquashSelection: ...
    def choose_squash_name(self, selection: SquashSelection) -> str: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def preflight_squash_controller(self, plan: SquashPlan) -> None: ...
    def transaction(self, label: str): ...
    def create_squash_controller(self, plan: SquashPlan) -> None: ...
    def capture_squash_controller(self, control: str) -> tuple[str, str, int]: ...
    def resolve_squash_pair(self, selected_control: str) -> tuple[str, ...]: ...
    def delete_squash_controller(self, control: str) -> None: ...


class CreateSquashController:
    def __init__(self, host: SquashControllerHost):
        self._host = host

    def apply(self, base_name: str | None = None) -> SquashPlan:
        selection = self._host.capture_squash_selection()
        name = base_name or self._host.choose_squash_name(selection)
        plan = plan_squash_controller(selection, name)
        for node in plan.nodes:
            if self._host.find_name_collisions(node):
                raise ValueError("Squash 节点名称冲突：" + node)
        self._host.preflight_squash_controller(plan)
        with self._host.transaction("创建 Squash Controller"):
            self._host.create_squash_controller(plan)
            control, parent, joint_count = self._host.capture_squash_controller(
                plan.control)
            if (control.rsplit("|", 1)[-1].rsplit(":", 1)[-1] != plan.control
                    or parent != plan.parent_joint
                    or joint_count != 11):
                raise RuntimeError("Squash Controller 写后复检失败")
        return plan


class DeleteSquashController:
    def __init__(self, host: SquashControllerHost):
        self._host = host

    def apply(self, selected_control: str) -> tuple[str, ...]:
        controls = self._host.resolve_squash_pair(selected_control)
        if not controls:
            raise ValueError("未选中 Squash Controller")
        with self._host.transaction("删除 Squash Controller"):
            for control in controls:
                self._host.delete_squash_controller(control)
            for control in controls:
                if self._host.find_name_collisions(control):
                    raise RuntimeError("Squash Controller 删除复检失败：" + control)
        return controls
