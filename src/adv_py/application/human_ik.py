"""ADV Body Motion System HumanIK operations across the Maya host boundary."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.human_ik import (
    HumanIkAssignment, HumanIkBakePlan, HumanIkDefinitionPlan,
    plan_human_ik_bake, plan_human_ik_definition,
)


class HumanIkHost(Protocol):
    def capture_human_ik_nodes(self) -> frozenset[str]: ...
    def preflight_human_ik(self, operation: str) -> None: ...
    def transaction(self, label: str): ...
    def remove_human_ik(self) -> None: ...
    def create_human_ik_definition(self) -> None: ...
    def connect_human_ik_slot(self, assignment: HumanIkAssignment) -> None: ...
    def finish_human_ik_definition(self, create_control_rig: bool) -> None: ...
    def capture_human_ik_slots(self) -> dict[str, str]: ...
    def human_ik_exists(self) -> bool: ...
    def playback_range(self) -> tuple[float, float]: ...
    def bake_human_ik(self, plan: HumanIkBakePlan) -> None: ...
    def capture_baked_human_ik(self, plan: HumanIkBakePlan) -> bool: ...


class CreateHumanIk:
    def __init__(self, host: HumanIkHost):
        self._host = host

    def apply(self, *, create_control_rig: bool = True
              ) -> HumanIkDefinitionPlan:
        plan = plan_human_ik_definition(
            self._host.capture_human_ik_nodes(),
            create_control_rig=create_control_rig)
        self._host.preflight_human_ik("create")
        with self._host.transaction("创建 HumanIK"):
            self._host.remove_human_ik()
            self._host.create_human_ik_definition()
            for assignment in plan.assignments:
                self._host.connect_human_ik_slot(assignment)
            self._host.finish_human_ik_definition(plan.create_control_rig)
            slots = self._host.capture_human_ik_slots()
            if any(slots.get(item.slot) != item.source
                   for item in plan.assignments):
                raise RuntimeError("HumanIK 角色槽位写后复检失败")
        return plan


class DeleteHumanIk:
    def __init__(self, host: HumanIkHost):
        self._host = host

    def apply(self) -> None:
        self._host.preflight_human_ik("delete")
        with self._host.transaction("删除 HumanIK"):
            self._host.remove_human_ik()
            if self._host.human_ik_exists():
                raise RuntimeError("HumanIK 删除复检失败")


class BakeHumanIk:
    def __init__(self, host: HumanIkHost):
        self._host = host

    def apply(self) -> HumanIkBakePlan:
        first, last = self._host.playback_range()
        plan = plan_human_ik_bake(
            self._host.capture_human_ik_nodes(), first, last)
        self._host.preflight_human_ik("bake")
        with self._host.transaction("烘焙 HumanIK 到 ADV 控制器"):
            self._host.bake_human_ik(plan)
            if not self._host.capture_baked_human_ik(plan):
                raise RuntimeError("HumanIK 烘焙复检失败")
        return plan
