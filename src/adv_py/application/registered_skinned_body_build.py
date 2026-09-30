"""Build a registered Body and bind its meshes in one scene transaction."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_part_twist import FitPartTwistSource
from adv_py.core.skin_bind import (
    SmoothBindPreferences, SkinBindMethod, audit_skin_bind_result,
)

from .registered_body_build import (BuildRegisteredBodyCharacter,
                                    RegisteredBodyBuildResult,
                                    _JoinedTransactionHost)
from .body_selection_sets import finalize_body_character_sets
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
    smooth_bind: SmoothBindPreferences


class BuildRegisteredSkinnedBodyCharacter:
    def __init__(self, host):
        self._host = host

    def plan(self, meshes: tuple[str, ...], *,
             skin_prefix: str = "AdvPy_BodySkin",
             maximum_influences: int | None = None) -> RegisteredSkinnedBodyBuildPlan:
        if (not meshes or any(not isinstance(mesh, str) or not mesh.strip()
                              for mesh in meshes)
                or len(set(meshes)) != len(meshes)
                or maximum_influences is not None and (
                    type(maximum_influences) is not int
                    or not 1 <= maximum_influences <= 256)):
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
        read_options = getattr(self._host,
                               "read_body_smooth_bind_options", None)
        options = (read_options() if read_options is not None
                   else SmoothBindPreferences())
        if not isinstance(options, SmoothBindPreferences):
            raise FitSkeletonValidationError(
                "Maya Smooth Bind 选项快照无效")
        return RegisteredSkinnedBodyBuildPlan(
            meshes, skin_names,
            (options.maximum_influences if maximum_influences is None
             else maximum_influences), options)

    def apply(self, meshes: tuple[str, ...], *,
              container_name: str = "FitSkeleton",
              skin_prefix: str = "AdvPy_BodySkin",
              maximum_influences: int | None = None,
              axial_description=None,
              include_head_aim: bool = False,
              infer_missing_labels: bool = False,
              include_segment_influences: bool = True,
              use_fit_part_hierarchy: bool = True,
              fit_part_twist_sources: tuple[FitPartTwistSource, ...] | None = None,
              on_stage=None,
              _scene_before=None) -> RegisteredSkinnedBodyBuildResult:
        plan = self.plan(meshes, skin_prefix=skin_prefix,
                         maximum_influences=maximum_influences)
        mesh_ids = tuple(self._host.capture_body_mesh_identity(mesh)
                         for mesh in plan.meshes)
        if len(set(mesh_ids)) != len(mesh_ids):
            raise FitSkeletonValidationError(
                "同一网格被多个路径重复提交给 Body Skin")
        scene_before = (_scene_before if _scene_before is not None
                        else self._host.capture_body_scene_nodes())
        with self._host.transaction("从 Fit 构建完整蒙皮角色"):
            joined = _JoinedTransactionHost(self._host)
            character = BuildRegisteredBodyCharacter(joined).apply(
                container_name, axial_description=axial_description,
                include_head_aim=include_head_aim,
                infer_missing_labels=infer_missing_labels,
                include_segment_influences=include_segment_influences,
                use_fit_part_hierarchy=use_fit_part_hierarchy,
                fit_part_twist_sources=fit_part_twist_sources,
                _scene_before=scene_before,
                _defer_all_set=True)
            if on_stage:
                on_stage("rig-built")
            _, influences = joined.resolve_body_selection_members(
                character.registration, character.segment_influences,
                character.selection_extras)
            influences = tuple(
                path for path in influences
                if path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                not in {"Eye_R", "Eye_L", "Jaw_M"})
            if not influences:
                raise FitSkeletonValidationError(
                    "DeformSet 没有可用于 Skin 的影响关节")
            geometry_meshes = tuple(
                joined.parent_body_mesh_under_geometry(
                    joined.resolve_body_mesh_identity(identifier))
                for identifier in mesh_ids)
            binder = BindSkin(joined)
            def options(name):
                return dict(
                    skin_name=name,
                    maximum_influences=plan.maximum_influences,
                    maintain_maximum_influences=(
                        plan.smooth_bind.maintain_maximum_influences),
                    bind_method=plan.smooth_bind.bind_method,
                    normalization=plan.smooth_bind.normalization,
                    skinning_method=plan.smooth_bind.skinning_method,
                    remove_unused_influences=(
                        plan.smooth_bind.remove_unused_influences),
                    weight_distribution=(
                        plan.smooth_bind.weight_distribution))
            if (plan.smooth_bind.bind_method is SkinBindMethod.GEODESIC_VOXEL
                    and len(geometry_meshes) > 1):
                # Voxel binding sees the entire volume at once. Solving each
                # mesh independently produces different seam weights.
                bind_plans = tuple(binder.plan(mesh, influences, **options(name))
                    for mesh, name in zip(geometry_meshes, plan.skin_names))
                for item in bind_plans:
                    if not item.ready:
                        raise FitSkeletonValidationError(
                            "Skin Bind 预检失败：" + "；".join(item.blockers))
                    if joined.capture_skin_bind_input(item.bind) != item.input_state:
                        raise FitSkeletonValidationError("Skin Bind 输入在执行前发生变化")
                    joined.create_skin_bind(item.bind, defer_geodesic=True)
                joined.solve_geodesic_skin_binds(
                    tuple(item.bind for item in bind_plans))
                results = []
                for item in bind_plans:
                    snapshot = joined.capture_skin_bind(item.bind)
                    issues = audit_skin_bind_result(item.bind, snapshot)
                    if issues:
                        raise RuntimeError("批量 Geodesic Skin 结果不符："
                            + "；".join(issue.message for issue in issues))
                    results.append(SkinBindBuildResult(item, snapshot))
                skins = tuple(results)
                if len({item.snapshot.geodesic_source.split('.', 1)[0]
                        for item in skins}) != 1:
                    raise RuntimeError("多网格 Geodesic 没有共享体素求解节点")
            else:
                skins = tuple(binder.apply(mesh, influences, **options(name))
                    for mesh, name in zip(geometry_meshes, plan.skin_names))
            finalize_body_character_sets(
                joined, character.registration, character.rig.plan,
                scene_before=scene_before, fit_container=container_name,
                create_sets=False)
            if on_stage:
                on_stage("skins-bound")
        return RegisteredSkinnedBodyBuildResult(character, skins)
