"""Build and remove Mannequin geometry with host readback."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.geometry_mannequin import (
    MannequinPiece, MannequinSegment, plan_mannequin,
)


class MannequinHost(Protocol):
    def capture_mannequin_input(self) -> tuple[tuple[MannequinSegment, ...], float]: ...
    def preflight_mannequin(self, plan: tuple[MannequinPiece, ...]) -> None: ...
    def transaction(self, label: str): ...
    def create_mannequin(self, plan: tuple[MannequinPiece, ...]) -> int: ...
    def capture_mannequin(self, count: int) -> bool: ...
    def mannequin_exists(self) -> bool: ...
    def delete_mannequin(self) -> None: ...


class CreateMannequin:
    def __init__(self, host: MannequinHost) -> None:
        self.host = host

    def execute(self) -> int:
        segments, height = self.host.capture_mannequin_input()
        plan = plan_mannequin(segments, height)
        self.host.preflight_mannequin(plan)
        with self.host.transaction("创建 Mannequin"):
            count = self.host.create_mannequin(plan)
            if not self.host.capture_mannequin(count):
                raise RuntimeError("Mannequin 创建结果不完整")
        return count


class DeleteMannequin:
    def __init__(self, host: MannequinHost) -> None:
        self.host = host

    def execute(self) -> None:
        if not self.host.mannequin_exists():
            return
        with self.host.transaction("删除 Mannequin"):
            self.host.delete_mannequin()
            if self.host.mannequin_exists():
                raise RuntimeError("Mannequin 删除后仍有生成物")
