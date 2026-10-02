"""Build a one-joint prop from the original Preparation Skin and All inputs."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.body_build_options import BodyBuildOptions


@dataclass(frozen=True, slots=True)
class OneJointPropResult:
    fit_root: str
    deform_joint: str
    control: str
    meshes: tuple[str, ...]
    skins: tuple[str, ...]


class BuildOneJointProp:
    def __init__(self, host) -> None:
        self._host = host

    def apply(self, skin_meshes: tuple[str, ...], all_meshes: tuple[str, ...],
              *, build_options=None, on_stage=None) -> OneJointPropResult:
        if not skin_meshes or len(set(skin_meshes)) != len(skin_meshes):
            raise FitSkeletonValidationError("One Joint Prop 需要不重复的 Skin 模型")
        if build_options is not None and not isinstance(build_options, BodyBuildOptions):
            raise FitSkeletonValidationError('One Joint Prop Body 构建选项无效')
        meshes = tuple(dict.fromkeys((*skin_meshes, *all_meshes)))
        source_states = tuple(self._host.capture_body_mesh_bind_source(mesh)
                              for mesh in meshes)
        names = ("FitSkeleton", "Root", "Group", "Root_M", "Main")
        for name in names:
            if self._host.find_name_collisions(name):
                raise FitSkeletonValidationError("One Joint Prop 名称已被占用：" + name)
        skin_names = tuple("AdvPy_PropSkin" if index == 0 else
                           f"AdvPy_PropSkin_{index + 1}"
                           for index in range(len(meshes)))
        for name in skin_names:
            if self._host.find_name_collisions(name):
                raise FitSkeletonValidationError("One Joint Prop Skin 名称已被占用：" + name)
        with self._host.transaction("从 Preparation 构建单关节道具"):
            fit, joint, control = self._host.create_one_joint_prop_rig(
                skin_meshes[0], skin_meshes=skin_meshes,
                all_meshes=all_meshes, build_options=build_options)
            for mesh, original in zip(meshes, source_states):
                if not original.matches(
                        self._host.capture_body_mesh_bind_source(mesh)):
                    raise FitSkeletonValidationError(
                        "单关节道具构建改变了待绑定网格：" + mesh)
            if on_stage:
                on_stage("rig-built")
            skins = self._host.bind_one_joint_prop_meshes(meshes, joint, skin_names)
            if on_stage:
                on_stage("skins-bound")
            meshes = self._host.finalize_one_joint_prop_geometry(meshes, skin_meshes[0])
            if on_stage:
                on_stage("geometry-parented")
        return OneJointPropResult(fit, joint, control, meshes, skins)
