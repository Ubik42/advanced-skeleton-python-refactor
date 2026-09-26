"""Build a one-joint prop from the original Preparation Skin and All inputs."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_bind import plan_skin_bind


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
              *, on_stage=None) -> OneJointPropResult:
        if not skin_meshes or len(set(skin_meshes)) != len(skin_meshes):
            raise FitSkeletonValidationError("One Joint Prop 需要不重复的 Skin 模型")
        meshes = tuple(dict.fromkeys((*skin_meshes, *all_meshes)))
        for mesh in meshes:
            self._host.preflight_body_mesh(mesh)
        names = ("FitSkeleton", "Root", "Group", "Rig", "Root_M", "Main")
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
                skin_meshes[0])
            if on_stage:
                on_stage("rig-built")
            for mesh, skin_name in zip(meshes, skin_names):
                bind = plan_skin_bind(mesh, (joint,), skin_name=skin_name,
                                      maximum_influences=1)
                self._host.create_skin_bind(bind)
                self._host.capture_skin_bind(bind)
            if on_stage:
                on_stage("skins-bound")
        return OneJointPropResult(fit, joint, control, meshes, skin_names)
