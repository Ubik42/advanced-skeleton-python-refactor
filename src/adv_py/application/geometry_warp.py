"""Create and delete original-style PolyBoxes Warp geometry."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.geometry_warp import WarpSpec, plan_warps


class WarpHost(Protocol):
    def capture_selected_meshes(self) -> tuple[str, ...]: ...
    def all_box_names(self) -> tuple[str, ...]: ...
    def capture_warp_names(self) -> frozenset[str]: ...
    def preflight_warp(self, plan: tuple[WarpSpec, ...]) -> None: ...
    def transaction(self, label: str): ...
    def create_warp(self, plan: tuple[WarpSpec, ...]) -> int: ...
    def capture_warp(self, count: int) -> bool: ...
    def warp_exists(self) -> bool: ...
    def delete_warp(self) -> None: ...


class CreateWarp:
    def __init__(self, host: WarpHost) -> None:
        self.host = host

    def execute(self) -> int:
        plan = plan_warps(self.host.capture_selected_meshes(),
                          self.host.all_box_names(),
                          self.host.capture_warp_names())
        self.host.preflight_warp(plan)
        with self.host.transaction("创建 PolyBoxes Warp"):
            count = self.host.create_warp(plan)
            if not self.host.capture_warp(count):
                raise RuntimeError("PolyBoxes Warp 创建结果不完整")
        return count


class DeleteWarp:
    def __init__(self, host: WarpHost) -> None:
        self.host = host

    def execute(self) -> None:
        if not self.host.warp_exists():
            return
        with self.host.transaction("删除 PolyBoxes Warp"):
            self.host.delete_warp()
            if self.host.warp_exists():
                raise RuntimeError("PolyBoxes Warp 删除后仍有生成物")
