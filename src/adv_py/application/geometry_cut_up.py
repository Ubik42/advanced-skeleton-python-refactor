"""Geometry / Skin Cut-Up create and delete actions."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.geometry_cut_up import CutUpMeshPlan, plan_cut_up_mesh


class CutUpHost(Protocol):
    def capture_cut_up_inputs(self) -> tuple[tuple, ...]: ...
    def preflight_cut_up(self, plans: tuple[CutUpMeshPlan, ...]) -> None: ...
    def transaction(self, label: str): ...
    def create_cut_up(self, plan: CutUpMeshPlan) -> int: ...
    def finalize_cut_up(self, plans: tuple[CutUpMeshPlan,...]) -> int: ...
    def capture_cut_up(self, plans: tuple[CutUpMeshPlan, ...]) -> bool: ...
    def delete_cut_up(self) -> None: ...
    def cut_up_exists(self) -> bool: ...


class CreateGeometryCutUp:
    def __init__(self, host: CutUpHost) -> None:
        self.host = host

    def execute(self) -> int:
        plans = tuple(plan_cut_up_mesh(*row) for row in
                      self.host.capture_cut_up_inputs())
        self.host.preflight_cut_up(plans)
        with self.host.transaction("按 Skin 权重创建 Cut-Up 几何"):
            for plan in plans:self.host.create_cut_up(plan)
            count = self.host.finalize_cut_up(plans)
            if not self.host.capture_cut_up(plans):
                raise RuntimeError("Skin Cut-Up 创建后分片数量或关节跟随缺失")
        return count


class DeleteGeometryCutUp:
    def __init__(self, host: CutUpHost) -> None:
        self.host = host

    def execute(self) -> None:
        if not self.host.cut_up_exists():
            return
        with self.host.transaction("删除 Skin Cut-Up 几何"):
            self.host.delete_cut_up()
            if self.host.cut_up_exists():
                raise RuntimeError("Skin Cut-Up 删除后仍有生成物")
