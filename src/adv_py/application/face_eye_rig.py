"""Build paired eye controls and rigid eye skins under a Body head joint."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_bind import plan_skin_bind


@dataclass(frozen=True, slots=True)
class FaceEyeRigResult:
    group: str
    global_control: str
    right_control: str
    left_control: str
    right_joint: str
    left_joint: str
    skins: tuple[str, str]


class BuildFaceEyeRig:
    def __init__(self, host) -> None:
        self._host = host

    def apply(self, head_joint: str, right_eye: str, left_eye: str,
              *, on_stage=None) -> FaceEyeRigResult:
        if not head_joint or not right_eye or not left_eye:
            raise FitSkeletonValidationError("双眼构建需要 Head 关节与左右眼网格")
        if right_eye == left_eye:
            raise FitSkeletonValidationError("左右眼必须是不同网格")
        self._host.preflight_face_eye_head(head_joint)
        for mesh in (right_eye, left_eye):
            self._host.preflight_body_mesh(mesh)
        names = ("AdvPy_FaceEyes", "AdvPy_EyeAim", "AdvPy_EyeAim_R",
                 "AdvPy_EyeAim_L", "AdvPy_Eye_R", "AdvPy_Eye_L",
                 "AdvPy_EyeSkin_R", "AdvPy_EyeSkin_L")
        for name in names:
            if self._host.find_name_collisions(name):
                raise FitSkeletonValidationError("眼部节点名称已被占用：" + name)
        with self._host.transaction("从 Face Pre 构建双眼控制与蒙皮"):
            result = self._host.create_face_eye_rig(
                head_joint, right_eye, left_eye)
            if on_stage:
                on_stage("controls-built")
            for mesh, joint, skin in ((right_eye, result.right_joint,
                                       result.skins[0]),
                                      (left_eye, result.left_joint,
                                       result.skins[1])):
                plan = plan_skin_bind(mesh, (joint,), skin_name=skin,
                                      maximum_influences=1)
                self._host.create_skin_bind(plan)
                self._host.capture_skin_bind(plan)
            if on_stage:
                on_stage("skins-bound")
        return result
