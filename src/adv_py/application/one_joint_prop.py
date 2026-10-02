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
        if not skin_meshes:
            raise FitSkeletonValidationError('No object defined as "Skin"')
        if build_options is not None and not isinstance(build_options, BodyBuildOptions):
            raise FitSkeletonValidationError('One Joint Prop Body 构建选项无效')
        meshes = tuple(dict.fromkeys((*skin_meshes, *all_meshes)))
        self._host.preflight_one_joint_prop(skin_meshes, all_meshes)
        with self._host.transaction("从 Preparation 构建单关节道具"):
            fit, joint, control = self._host.create_one_joint_prop_rig(
                skin_meshes[0], skin_meshes=skin_meshes,
                all_meshes=all_meshes, build_options=build_options)
            if on_stage:
                on_stage("rig-built")
            skins = self._host.bind_one_joint_prop_meshes(meshes, joint)
            if on_stage:
                on_stage("skins-bound")
            meshes = self._host.finalize_one_joint_prop_geometry(meshes, skin_meshes[0])
            if on_stage:
                on_stage("geometry-parented")
        return OneJointPropResult(fit, joint, control, meshes, skins)
