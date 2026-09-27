"""Source skeleton to Fit, Body, controls and Skin without DCC dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .character_from_fit import (BuildCharacterFromFit,
                                 CharacterFromFitHost,
                                 CharacterFromFitResult)
from .registered_body_build import _JoinedTransactionHost
from .source_skeleton_fit import (BuildFitFromSourceSkeleton,
                                  SourceSkeletonFitHost,
                                  SourceSkeletonFitPlan,
                                  SourceSkeletonFitResult)


class CharacterFromSourceHost(SourceSkeletonFitHost,
                              CharacterFromFitHost, Protocol):
    pass


@dataclass(frozen=True, slots=True)
class SourceCharacterBuildResult:
    fit: SourceSkeletonFitResult
    character: CharacterFromFitResult


@dataclass(frozen=True, slots=True)
class SourceCharacterBuildPlan:
    source_root: str
    container: str
    meshes: tuple[str, ...]
    maximum_influences: int
    include_head_aim: bool
    include_segment_influences: bool
    fit: SourceSkeletonFitPlan


class BuildCharacterFromSourceSkeleton:
    """Preserve the source hierarchy and make a separately owned character."""

    def __init__(self, host: CharacterFromSourceHost):
        self._host = host

    def plan(self, source_root: str, container: str = "FitSkeleton", *,
             meshes: tuple[str, ...] = (),
             maximum_influences: int = 4,
             include_head_aim: bool = False,
             include_segment_influences: bool = True,
             ) -> SourceCharacterBuildPlan:
        if not source_root.strip() or not container.strip():
            raise ValueError("来源根关节与 Fit 容器名称不能为空")
        if (len(meshes) != len(set(meshes)) or any(not mesh.strip()
                for mesh in meshes)):
            raise ValueError("待绑定网格路径不能为空或重复")
        if (isinstance(maximum_influences, bool)
                or not isinstance(maximum_influences, int)
                or not 1 <= maximum_influences <= 256):
            raise ValueError("最大影响关节数须为 1..256 的整数")
        fit = BuildFitFromSourceSkeleton(self._host).plan(source_root)
        return SourceCharacterBuildPlan(source_root, container, meshes,
            maximum_influences, include_head_aim,
            include_segment_influences, fit)

    def apply(self, source_root: str, container: str = "FitSkeleton", *,
              meshes: tuple[str, ...] = (),
              maximum_influences: int = 4,
              include_head_aim: bool = False,
              include_segment_influences: bool = True,
              ) -> SourceCharacterBuildResult:
        plan = self.plan(source_root, container, meshes=meshes,
            maximum_influences=maximum_influences,
            include_head_aim=include_head_aim,
            include_segment_influences=include_segment_influences)
        with self._host.transaction("从标准骨架构建并蒙皮角色"):
            joined = _JoinedTransactionHost(self._host)
            fit = BuildFitFromSourceSkeleton(joined).apply_plan(
                plan.fit, plan.container)
            character = BuildCharacterFromFit(joined).apply(
                plan.container, meshes=plan.meshes,
                spine_segments=fit.spine_segments,
                maximum_influences=plan.maximum_influences,
                include_head_aim=plan.include_head_aim,
                include_segment_influences=plan.include_segment_influences)
        return SourceCharacterBuildResult(fit, character)
