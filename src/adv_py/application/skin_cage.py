"""SkinCage operations using the 6.925 scene structure."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.skin_cage import (
    SkinCageBuildPlan, SkinCageCopyTarget, SkinCageMirrorPair,
    SkinCageWidthInput, SkinCageWidthSpec,
    plan_skin_cage_build, plan_skin_cage_copy, plan_skin_cage_mirror,
    plan_skin_cage_width,
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
    def capture_mirror_input(self) -> tuple[str, ...]: ...
    def preflight_mirror(self, pairs: tuple[SkinCageMirrorPair, ...]) -> None: ...
    def mirror_profiles(self, pair: SkinCageMirrorPair) -> None: ...
    def capture_mirror(self, pair: SkinCageMirrorPair) -> bool: ...
    def capture_width_input(self) -> tuple[SkinCageWidthInput, ...]: ...
    def preflight_width(self, specs: tuple[SkinCageWidthSpec, ...]) -> None: ...
    def set_width(self, spec: SkinCageWidthSpec) -> None: ...
    def capture_width(self, spec: SkinCageWidthSpec) -> bool: ...
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


class MirrorSkinCage:
    def __init__(self, host: SkinCageHost) -> None:
        self._host = host

    def execute(self, source_side: str) -> int:
        pairs = plan_skin_cage_mirror(
            self._host.capture_mirror_input(), source_side)
        self._host.preflight_mirror(pairs)
        with self._host.transaction("镜像 SkinCage 曲线"):
            for pair in pairs:
                self._host.mirror_profiles(pair)
            for pair in pairs:
                if not self._host.capture_mirror(pair):
                    raise RuntimeError("SkinCage 镜像后曲线形状不一致：" +
                                       pair.target)
        return len(pairs)


class SetSkinCageDeformationWidth:
    def __init__(self, host: SkinCageHost) -> None:
        self._host = host

    def execute(self) -> int:
        specs = plan_skin_cage_width(self._host.capture_width_input())
        self._host.preflight_width(specs)
        with self._host.transaction("调整 SkinCage DeformationWidth"):
            for spec in specs:
                self._host.set_width(spec)
            for spec in specs:
                if not self._host.capture_width(spec):
                    raise RuntimeError("SkinCage 宽度权重写入后读回不一致：" +
                                       spec.source.profile)
        return len(specs)


class DeleteSkinCage:
    def __init__(self, host: SkinCageHost) -> None:
        self._host = host

    def execute(self) -> int:
        with self._host.transaction("删除 SkinCage"):
            return len(self._host.delete_cage())
