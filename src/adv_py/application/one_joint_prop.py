"""Build a one-joint prop from the original Preparation Skin and All inputs."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_bind import (
    SmoothBindPreferences, audit_skin_bind_result, plan_skin_bind,
)


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
        read_options = getattr(self._host,
                               "read_body_smooth_bind_options", None)
        options = (read_options() if read_options is not None
                   else SmoothBindPreferences())
        if not isinstance(options, SmoothBindPreferences):
            raise FitSkeletonValidationError(
                "One Joint Prop Smooth Bind 选项快照无效")
        with self._host.transaction("从 Preparation 构建单关节道具"):
            fit, joint, control = self._host.create_one_joint_prop_rig(
                skin_meshes[0])
            if on_stage:
                on_stage("rig-built")
            for mesh, skin_name in zip(meshes, skin_names):
                bind = plan_skin_bind(mesh, (joint,), skin_name=skin_name,
                                      maximum_influences=(
                                          options.maximum_influences),
                                      maintain_maximum_influences=(
                                          options.maintain_maximum_influences),
                                      bind_method=options.bind_method,
                                      normalization=options.normalization,
                                      skinning_method=options.skinning_method,
                                      weight_distribution=(
                                          options.weight_distribution))
                self._host.create_skin_bind(bind)
                issues = audit_skin_bind_result(
                    bind, self._host.capture_skin_bind(bind))
                if issues:
                    raise RuntimeError(
                        "One Joint Prop Skin 结果不符合原绑定设置："
                        + "；".join(issue.message for issue in issues))
            if on_stage:
                on_stage("skins-bound")
        return OneJointPropResult(fit, joint, control, meshes, skin_names)
