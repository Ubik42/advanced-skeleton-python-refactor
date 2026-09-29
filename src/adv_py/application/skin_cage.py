"""SkinCage operations using the 6.925 scene structure."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.skin_cage import (
    SkinCageBuildPlan, SkinCageCopyTarget, plan_skin_cage_build,
    plan_skin_cage_copy,
)


class SkinCageHost(Protocol):
    def capture_build_input(self): ...
    def preflight_build(self, plan: SkinCageBuildPlan) -> None: ...
    def create_cage(self, plan: SkinCageBuildPlan) -> None: ...
    def capture_build(self, plan: SkinCageBuildPlan) -> bool: ...
    def capture_copy_input(self) -> tuple[tuple[str, ...], tuple[str, ...]]: ...
    def preflight_copy(self, targets: tuple[SkinCageCopyTarget, ...]) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def copy_weights(self, target: SkinCageCopyTarget) -> None: ...
    def capture_copy(self, target: SkinCageCopyTarget) -> bool: ...
    def delete_cage(self) -> tuple[str, ...]: ...
    def print_reuse_commands(self, *, transforms: bool, shapes: bool,
                             catch: bool) -> int: ...


class CopySkinCageWeights:
    def __init__(self, host: SkinCageHost) -> None:
        self._host = host

    def execute(self) -> int:
        targets = plan_skin_cage_copy(*self._host.capture_copy_input())
        self._host.preflight_copy(targets)
        with self._host.transaction("复制 SkinCage 权重"):
            for target in targets:
                self._host.copy_weights(target)
            for target in targets:
                if not self._host.capture_copy(target):
                    raise RuntimeError("SkinCage 权重复制后没有可读的目标蒙皮："
                                       + target.mesh)
        return len(targets)


class CreateSkinCage:
    def __init__(self, host: SkinCageHost) -> None:
        self._host = host

    def execute(self) -> int:
        plan = plan_skin_cage_build(*self._host.capture_build_input())
        self._host.preflight_build(plan)
        with self._host.transaction("创建 SkinCage"):
            self._host.create_cage(plan)
            if not self._host.capture_build(plan):
                raise RuntimeError("SkinCage 创建后缺少笼体、蒙皮或曲线")
        return len(plan.chains)


class DeleteSkinCage:
    def __init__(self, host: SkinCageHost) -> None:
        self._host = host

    def execute(self) -> int:
        with self._host.transaction("删除 SkinCage"):
            return len(self._host.delete_cage())
