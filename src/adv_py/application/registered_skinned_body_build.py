"""Build a registered Body and bind its meshes in one scene transaction."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError

from .registered_body_build import (BuildRegisteredBodyCharacter,
                                    RegisteredBodyBuildResult,
                                    _JoinedTransactionHost)
from .skin_bind import BindSkin, SkinBindBuildResult


@dataclass(frozen=True, slots=True)
class RegisteredSkinnedBodyBuildResult:
    character: RegisteredBodyBuildResult
    skins: tuple[SkinBindBuildResult, ...]


@dataclass(frozen=True, slots=True)
class RegisteredSkinnedBodyBuildPlan:
    meshes: tuple[str, ...]
    skin_names: tuple[str, ...]
    maximum_influences: int


class BuildRegisteredSkinnedBodyCharacter:
    def __init__(self, host):
        self._host = host

    def plan(self, meshes: tuple[str, ...], *,
             skin_prefix: str = "AdvPy_BodySkin",
             maximum_influences: int = 4) -> RegisteredSkinnedBodyBuildPlan:
        if (not meshes or any(not isinstance(mesh, str) or not mesh.strip()
                              for mesh in meshes)
                or len(set(meshes)) != len(meshes)
                or isinstance(maximum_influences, bool)
                or not isinstance(maximum_influences, int)
                or not 1 <= maximum_influences <= 256):
            raise ValueError("请提供不重复的网格和有效的最大影响关节数")
        if not isinstance(skin_prefix, str) or not skin_prefix.strip():
            raise ValueError("Skin 名称前缀不能为空")
        skin_names = tuple(skin_prefix if index == 0 else
                           f"{skin_prefix}_{index + 1}"
                           for index in range(len(meshes)))
        for mesh in meshes:
            self._host.preflight_body_mesh(mesh)
        for name in skin_names:
            if self._host.find_name_collisions(name):
                raise FitSkeletonValidationError("Skin 名称已被占用：" + name)
        return RegisteredSkinnedBodyBuildPlan(
            meshes, skin_names, maximum_influences)

    def apply(self, meshes: tuple[str, ...], *,
              container_name: str = "FitSkeleton",
              skin_prefix: str = "AdvPy_BodySkin",
              maximum_influences: int = 4,
              axial_description=None,
              include_head_aim: bool = False,
              infer_missing_labels: bool = False,
              include_segment_influences: bool = False,
              on_stage=None) -> RegisteredSkinnedBodyBuildResult:
        plan = self.plan(meshes, skin_prefix=skin_prefix,
                         maximum_influences=maximum_influences)
        with self._host.transaction("从 Fit 构建完整蒙皮角色"):
            joined = _JoinedTransactionHost(self._host)
            character = BuildRegisteredBodyCharacter(joined).apply(
                container_name, axial_description=axial_description,
                include_head_aim=include_head_aim,
                infer_missing_labels=infer_missing_labels,
                include_segment_influences=include_segment_influences)
            if on_stage:
                on_stage("rig-built")
            influences = tuple(path for path in (
                tuple(item.path for item in character.registration.body)
                + character.segment_influences)
                if joined.read_skin_influence_enabled(path))
            skins = tuple(BindSkin(joined).apply(mesh, influences,
                skin_name=name, maximum_influences=plan.maximum_influences)
                for mesh, name in zip(plan.meshes, plan.skin_names))
            if on_stage:
                on_stage("skins-bound")
        return RegisteredSkinnedBodyBuildResult(character, skins)
