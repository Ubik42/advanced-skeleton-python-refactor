"""Create and select original-style SkinLoop edge sets."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.skin_loops import (
    SkinLoopBindSpec, SkinLoopCopySpec, SkinLoopSpec,
    plan_skin_loop_bind, plan_skin_loop_copy, plan_skin_loops,
)


class SkinLoopsHost(Protocol):
    def capture_skin_loop_input(self, mirror: bool): ...
    def preflight_skin_loop(self, spec: SkinLoopSpec) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_skin_loop(self, spec: SkinLoopSpec) -> None: ...
    def capture_skin_loop(self, spec: SkinLoopSpec) -> bool: ...
    def select_all_skin_loops(self) -> int: ...
    def capture_skin_loop_copy_input(self): ...
    def preflight_skin_loop_copy(self, spec: SkinLoopCopySpec) -> None: ...
    def copy_skin_loop_weights(self, spec: SkinLoopCopySpec) -> None: ...
    def capture_skin_loop_copy(self, spec: SkinLoopCopySpec) -> bool: ...
    def capture_skin_loop_bind_input(self) -> tuple[SkinLoopBindSpec, ...]: ...
    def preflight_skin_loop_bind(self, spec: SkinLoopBindSpec) -> None: ...
    def bind_skin_loops(self, spec: SkinLoopBindSpec) -> None: ...
    def capture_skin_loop_bind(self, spec: SkinLoopBindSpec) -> bool: ...


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


class CopySkinLoopWeights:
    def __init__(self, host: SkinLoopsHost) -> None:
        self._host = host

    def execute(self) -> tuple[SkinLoopCopySpec, ...]:
        specs = plan_skin_loop_copy(*self._host.capture_skin_loop_copy_input())
        for spec in specs:
            self._host.preflight_skin_loop_copy(spec)
        with self._host.transaction("复制 SkinLoop 权重"):
            for spec in specs:
                self._host.copy_skin_loop_weights(spec)
            for spec in specs:
                if not self._host.capture_skin_loop_copy(spec):
                    raise RuntimeError("SkinLoop 权重复制后蒙皮结构不一致："
                                       + spec.target_mesh)
        return specs


class BindSkinLoops:
    def __init__(self, host: SkinLoopsHost) -> None:
        self._host = host

    def execute(self) -> tuple[SkinLoopBindSpec, ...]:
        specs = plan_skin_loop_bind(
            self._host.capture_skin_loop_bind_input())
        for spec in specs:
            self._host.preflight_skin_loop_bind(spec)
        with self._host.transaction("绑定 SkinLoops"):
            for spec in specs:
                self._host.bind_skin_loops(spec)
            for spec in specs:
                if not self._host.capture_skin_loop_bind(spec):
                    raise RuntimeError("SkinLoop Bind 输出不一致：" + spec.mesh)
        return specs
