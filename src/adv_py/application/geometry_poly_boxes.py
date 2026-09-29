"""Create, delete and mirror the original PolyBoxes geometry layer."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.geometry_poly_boxes import (
    PolyBoxSource, PolyBoxSpec, plan_poly_boxes, plan_poly_box_mirror,
)


class PolyBoxesHost(Protocol):
    def capture_sources(self) -> tuple[PolyBoxSource, ...]: ...
    def preflight_create(self, plan: tuple[PolyBoxSpec, ...]) -> None: ...
    def transaction(self, label: str): ...
    def create(self, plan: tuple[PolyBoxSpec, ...]) -> None: ...
    def capture_created(self, plan: tuple[PolyBoxSpec, ...]) -> bool: ...
    def exists(self) -> bool: ...
    def delete(self) -> None: ...
    def box_names(self) -> tuple[str, ...]: ...
    def mirror(self, pairs: tuple[tuple[str, str], ...]) -> int: ...


class CreatePolyBoxes:
    def __init__(self, host: PolyBoxesHost) -> None:
        self.host = host

    def execute(self) -> int:
        plan = plan_poly_boxes(self.host.capture_sources())
        self.host.preflight_create(plan)
        with self.host.transaction("创建 PolyBoxes"):
            self.host.create(plan)
            if not self.host.capture_created(plan):
                raise RuntimeError("PolyBoxes 创建结果不完整")
        return len(plan)


class DeletePolyBoxes:
    def __init__(self, host: PolyBoxesHost) -> None:
        self.host = host

    def execute(self) -> None:
        if not self.host.exists():
            return
        with self.host.transaction("删除 PolyBoxes"):
            self.host.delete()
            if self.host.exists():
                raise RuntimeError("PolyBoxes 删除后仍有生成物")


class MirrorPolyBoxes:
    def __init__(self, host: PolyBoxesHost) -> None:
        self.host = host

    def execute(self, source_side: str) -> int:
        pairs = plan_poly_box_mirror(self.host.box_names(), source_side)
        if not pairs:
            return 0
        with self.host.transaction("镜像 PolyBoxes"):
            return self.host.mirror(pairs)
