"""Create and select original-style SkinLoop edge sets."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.skin_loops import SkinLoopSpec, plan_skin_loops


class SkinLoopsHost(Protocol):
    def capture_skin_loop_input(self, mirror: bool): ...
    def preflight_skin_loop(self, spec: SkinLoopSpec) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_skin_loop(self, spec: SkinLoopSpec) -> None: ...
    def capture_skin_loop(self, spec: SkinLoopSpec) -> bool: ...
    def select_all_skin_loops(self) -> int: ...


class CreateSkinLoops:
    def __init__(self, host: SkinLoopsHost) -> None:
        self._host = host

    def execute(self, *, mirror: bool = True) -> tuple[SkinLoopSpec, ...]:
        source = self._host.capture_skin_loop_input(mirror)
        specs = plan_skin_loops(*source)
        for spec in specs:
            self._host.preflight_skin_loop(spec)
        with self._host.transaction("创建 SkinLoop"):
            for spec in specs:
                self._host.create_skin_loop(spec)
            for spec in specs:
                if not self._host.capture_skin_loop(spec):
                    raise RuntimeError("SkinLoop 创建后边集合不一致：" + spec.set_name)
        return specs


class SelectAllSkinLoops:
    def __init__(self, host: SkinLoopsHost) -> None:
        self._host = host

    def execute(self) -> int:
        return self._host.select_all_skin_loops()
