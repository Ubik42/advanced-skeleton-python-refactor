"""Create and delete PolyBoxes Boolean geometry in one Maya transaction."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.geometry_boolean import BooleanSpec, plan_booleans


class BooleanHost(Protocol):
    def capture_selected_meshes(self) -> tuple[str, ...]: ...
    def all_box_names(self) -> tuple[str, ...]: ...
    def preflight_boolean(self, plan: tuple[BooleanSpec, ...]) -> None: ...
    def transaction(self, label: str): ...
    def create_boolean(self, plan: tuple[BooleanSpec, ...]) -> int: ...
    def capture_boolean(self, count: int) -> bool: ...
    def boolean_exists(self) -> bool: ...
    def delete_boolean(self) -> None: ...


class CreateBoolean:
    def __init__(self, host: BooleanHost) -> None:
        self.host = host

    def execute(self) -> int:
        plan = plan_booleans(self.host.capture_selected_meshes(),
                             self.host.all_box_names())
        self.host.preflight_boolean(plan)
        with self.host.transaction("创建 PolyBoxes Boolean"):
            count = self.host.create_boolean(plan)
            if not self.host.capture_boolean(count):
                raise RuntimeError("PolyBoxes Boolean 创建结果不完整")
        return count


class DeleteBoolean:
    def __init__(self, host: BooleanHost) -> None:
        self.host = host

    def execute(self) -> None:
        if not self.host.boolean_exists():
            return
        with self.host.transaction("删除 PolyBoxes Boolean"):
            self.host.delete_boolean()
            if self.host.boolean_exists():
                raise RuntimeError("PolyBoxes Boolean 删除后仍有生成物")
