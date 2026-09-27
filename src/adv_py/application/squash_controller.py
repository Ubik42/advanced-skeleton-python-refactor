"""Application boundary for ADV's Body Squash Controller."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.squash_controller import (
    SquashPlan, SquashSelection, plan_mirrored_squash_selection,
    plan_squash_controller,
)


class SquashControllerHost(Protocol):
    def capture_squash_selection(self) -> SquashSelection: ...
    def choose_squash_name(self, selection: SquashSelection) -> str: ...
    def capture_squash_mirror_candidates(self, plan: SquashPlan
            ) -> tuple[str, tuple[tuple[str, tuple[float, float, float]], ...], str]: ...
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

    def apply(self, base_name: str | None = None, *,
              mirror: bool = True) -> tuple[SquashPlan, ...]:
        if not isinstance(mirror, bool):
            raise ValueError("Squash 镜像选项须为布尔值")
        selection = self._host.capture_squash_selection()
        name = base_name or self._host.choose_squash_name(selection)
        plan = plan_squash_controller(selection, name)
        plans = [plan]
        if mirror and plan.side == "_R":
            mesh, vertices, parent = self._host.capture_squash_mirror_candidates(plan)
            mirrored = plan_mirrored_squash_selection(
                plan, mesh, vertices, parent)
            plans.append(plan_squash_controller(mirrored, name))
        for item in plans:
            for node in item.nodes:
                if self._host.find_name_collisions(node):
                    raise ValueError("Squash 节点名称冲突：" + node)
            self._host.preflight_squash_controller(item)
        with self._host.transaction("创建 Squash Controller"):
            for item in plans:
                self._host.create_squash_controller(item)
            for item in plans:
                control, parent, joint_count = self._host.capture_squash_controller(
                    item.control)
                if (control.rsplit("|", 1)[-1].rsplit(":", 1)[-1] != item.control
                        or parent != item.parent_joint
                        or joint_count != 11):
                    raise RuntimeError("Squash Controller 写后复检失败")
        return tuple(plans)


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
