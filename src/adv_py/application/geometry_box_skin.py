"""Build the original combined BoxSkin mesh from PolyBoxes."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.geometry_box_skin import BoxSkinPair, plan_box_skin
from adv_py.core.geometry_poly_boxes import PolyBoxSpec, plan_poly_boxes


class BoxSkinHost(Protocol):
    def transaction(self, label: str): ...
    def exists(self) -> bool: ...
    def capture_sources(self): ...
    def preflight_create(self, plan: tuple[PolyBoxSpec, ...]) -> None: ...
    def create(self, plan: tuple[PolyBoxSpec, ...]) -> None: ...
    def capture_created(self, plan: tuple[PolyBoxSpec, ...]) -> bool: ...
    def delete(self) -> None: ...
    def all_box_names(self) -> tuple[str, ...]: ...
    def box_skin_exists(self) -> bool: ...
    def preflight_box_skin(self, pairs: tuple[BoxSkinPair, ...]) -> None: ...
    def create_box_skin(self, pairs: tuple[BoxSkinPair, ...]) -> int: ...
    def capture_box_skin(self, pairs: tuple[BoxSkinPair, ...],
                         vertex_count: int) -> bool: ...
    def delete_box_skin(self) -> None: ...


class CreateBoxSkin:
    def __init__(self, host: BoxSkinHost) -> None:
        self.host = host

    def execute(self) -> int:
        generated = None
        if not self.host.exists():
            generated = plan_poly_boxes(self.host.capture_sources())
            self.host.preflight_create(generated)
            names = tuple(spec.name for spec in generated)
        else:
            names = self.host.all_box_names()
        pairs = plan_box_skin(names)
        self.host.preflight_box_skin(pairs)
        with self.host.transaction("创建 BoxSkin"):
            if generated is not None:
                self.host.create(generated)
                if not self.host.capture_created(generated):
                    raise RuntimeError("临时 PolyBoxes 创建不完整")
                # Native transfer traverses the actual copied holder children,
                # including its order for coincident vertices.
                pairs = plan_box_skin(self.host.all_box_names())
                self.host.preflight_box_skin(pairs)
            self.host.delete_box_skin()
            count = self.host.create_box_skin(pairs)
            if not self.host.capture_box_skin(pairs, count):
                raise RuntimeError("BoxSkin 创建结果不完整")
            if generated is not None:
                self.host.delete()
                if self.host.exists():
                    raise RuntimeError("临时 PolyBoxes 未清理")
        return count


class DeleteBoxSkin:
    def __init__(self, host: BoxSkinHost) -> None:
        self.host = host

    def execute(self) -> None:
        if not self.host.box_skin_exists():
            return
        with self.host.transaction("删除 BoxSkin"):
            self.host.delete_box_skin()
            if self.host.box_skin_exists():
                raise RuntimeError("BoxSkin 删除后仍有生成物")
