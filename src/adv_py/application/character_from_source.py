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
from adv_py.core.variable_body_fit import variable_axial_description


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
    maximum_influences: int | None
    include_head_aim: bool
    include_segment_influences: bool
    use_fit_part_hierarchy: bool
    fit: SourceSkeletonFitPlan
    spine_segments: int | None = None


class BuildCharacterFromSourceSkeleton:
    """Preserve the source hierarchy and make a separately owned character."""

    def __init__(self, host: CharacterFromSourceHost):
        self._host = host

    def plan(self, source_root: str, container: str = "FitSkeleton", *,
             meshes: tuple[str, ...] = (),
             maximum_influences: int | None = None,
             include_head_aim: bool = False,
             spine_segments: int | None = None,
             include_segment_influences: bool = True,
             use_fit_part_hierarchy: bool = True,
             ) -> SourceCharacterBuildPlan:
        if not source_root.strip() or not container.strip():
            raise ValueError("来源根关节与 Fit 容器名称不能为空")
        if (len(meshes) != len(set(meshes)) or any(not mesh.strip()
                for mesh in meshes)):
            raise ValueError("待绑定网格路径不能为空或重复")
        if (maximum_influences is not None and (
                type(maximum_influences) is not int
                or not 1 <= maximum_influences <= 256)):
            raise ValueError("最大影响关节数须为 1..256 的整数")
        if use_fit_part_hierarchy and not include_segment_influences:
            raise ValueError("Fit Part／Inbetween 需要启用分段 Skin 影响")
        if spine_segments is not None:
            variable_axial_description(spine_segments)
        fit = BuildFitFromSourceSkeleton(self._host).plan(source_root)
        if (spine_segments is not None
                and spine_segments != fit.spine_segments):
            raise ValueError(
                f"来源骨架有 {fit.spine_segments} 段脊柱，"
                f"构建选项要求 {spine_segments} 段")
        return SourceCharacterBuildPlan(source_root, container, meshes,
            maximum_influences, include_head_aim,
            include_segment_influences, use_fit_part_hierarchy, fit,
            spine_segments)

    def apply(self, source_root: str, container: str = "FitSkeleton", *,
              meshes: tuple[str, ...] = (),
              maximum_influences: int | None = None,
              include_head_aim: bool = False,
              spine_segments: int | None = None,
              include_segment_influences: bool = True,
              use_fit_part_hierarchy: bool = True,
              ) -> SourceCharacterBuildResult:
        plan = self.plan(source_root, container, meshes=meshes,
            maximum_influences=maximum_influences,
            include_head_aim=include_head_aim,
            spine_segments=spine_segments,
            include_segment_influences=include_segment_influences,
            use_fit_part_hierarchy=use_fit_part_hierarchy)
        with self._host.transaction("从标准骨架构建并蒙皮角色"):
            joined = _JoinedTransactionHost(self._host)
            fit = BuildFitFromSourceSkeleton(joined).apply_plan(
                plan.fit, plan.container)
            character = BuildCharacterFromFit(joined).apply(
                plan.container, meshes=plan.meshes,
                spine_segments=(plan.spine_segments if
                                plan.spine_segments is not None else
                                fit.spine_segments),
                maximum_influences=plan.maximum_influences,
                include_head_aim=plan.include_head_aim,
                include_segment_influences=plan.include_segment_influences,
                use_fit_part_hierarchy=plan.use_fit_part_hierarchy)
        return SourceCharacterBuildResult(fit, character)
