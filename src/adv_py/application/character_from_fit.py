"""Build a character from Fit, keeping external meshes outside the source rig."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.fit_hierarchy import FitHierarchySnapshot
from adv_py.core.variable_body_fit import axial_description_from_fit

from .axial_part_deform import AxialPartHost
from .body_character_rig import BodyCharacterRigHost
from .character_registry import CharacterRegistryHost
from .finger_mid_deform import FingerMidHost
from .limb_part_deform import LimbPartHost
from .oriented_body_skeleton import OrientedBodySkeletonHost
from .registered_body_build import (BuildRegisteredBodyCharacter,
                                    RegisteredBodyBuildResult,
                                    _JoinedTransactionHost)
from .registered_skinned_body_build import BuildRegisteredSkinnedBodyCharacter
from .skin_bind import SkinBindHost
from .skin_bind import SkinBindBuildResult


class CharacterFromFitHost(OrientedBodySkeletonHost, BodyCharacterRigHost,
                           CharacterRegistryHost, SkinBindHost,
                           AxialPartHost, FingerMidHost, LimbPartHost,
                           Protocol):
    """Scene operations used by the complete Fit-to-skinned-Body chain."""

    def capture_fit_hierarchy(self, container: str) -> FitHierarchySnapshot: ...
    def copy_external_mesh_for_character(self, mesh: str) -> str: ...
    def preflight_body_mesh(self, mesh: str) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class CharacterFromFitPlan:
    container: str
    meshes: tuple[str, ...]
    axial_description: BodyAxialDescription | None
    maximum_influences: int
    include_head_aim: bool
    infer_missing_labels: bool
    include_segment_influences: bool


@dataclass(frozen=True, slots=True)
class CharacterFromFitResult:
    body: RegisteredBodyBuildResult
    skins: tuple[SkinBindBuildResult, ...]


class BuildCharacterFromFit:
    """Construct Body, controls and optional Skin in one host transaction."""

    def __init__(self, host: CharacterFromFitHost):
        self._host = host

    def plan(self, container: str = "FitSkeleton", *,
             meshes: tuple[str, ...] = (),
             spine_segments: int | None = None,
             maximum_influences: int = 4,
             include_head_aim: bool = False,
             infer_missing_labels: bool = False,
             include_segment_influences: bool = False,
             ) -> CharacterFromFitPlan:
        if not container.strip():
            raise ValueError("Fit 容器名称不能为空")
        if (len(meshes) != len(set(meshes)) or any(not mesh.strip()
                for mesh in meshes)):
            raise ValueError("待绑定网格路径不能为空或重复")
        if (isinstance(maximum_influences, bool)
                or not isinstance(maximum_influences, int)
                or not 1 <= maximum_influences <= 256):
            raise ValueError("最大影响关节数须为 1..256 的整数")
        description = axial_description_from_fit(
            self._host.capture_fit_hierarchy(container), spine_segments)
        return CharacterFromFitPlan(container, meshes, description,
            maximum_influences, include_head_aim, infer_missing_labels,
            include_segment_influences)

    def apply(self, container: str = "FitSkeleton", *,
              meshes: tuple[str, ...] = (),
              spine_segments: int | None = None,
              maximum_influences: int = 4,
              include_head_aim: bool = False,
              infer_missing_labels: bool = False,
              include_segment_influences: bool = False,
              ) -> CharacterFromFitResult:
        plan = self.plan(container, meshes=meshes,
            spine_segments=spine_segments,
            maximum_influences=maximum_influences,
            include_head_aim=include_head_aim,
            infer_missing_labels=infer_missing_labels,
            include_segment_influences=include_segment_influences)
        if not plan.meshes:
            character = BuildRegisteredBodyCharacter(self._host).apply(
                plan.container, axial_description=plan.axial_description,
                include_head_aim=plan.include_head_aim,
                infer_missing_labels=plan.infer_missing_labels,
                include_segment_influences=plan.include_segment_influences)
            return CharacterFromFitResult(character, ())
        with self._host.transaction("复制模型并构建蒙皮角色"):
            joined = _JoinedTransactionHost(self._host)
            local_meshes = tuple(
                self._host.copy_external_mesh_for_character(mesh)
                for mesh in plan.meshes)
            built = BuildRegisteredSkinnedBodyCharacter(joined).apply(
                local_meshes, container_name=plan.container,
                maximum_influences=plan.maximum_influences,
                axial_description=plan.axial_description,
                include_head_aim=plan.include_head_aim,
                infer_missing_labels=plan.infer_missing_labels,
                include_segment_influences=plan.include_segment_influences)
            return CharacterFromFitResult(built.character, built.skins)
