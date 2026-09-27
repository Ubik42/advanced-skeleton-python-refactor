"""Coordinate bilateral Fit preparation and the eyelid scene build."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.face_eyelid_build_preparation import (
    FaceEyeLidPreparationInput, plan_face_eye_lid_preparation,
)
from adv_py.core.face_eyelid_build_mode import (
    FaceEyeLidBuildMode, plan_face_eye_lid_build_mode,
)
from adv_py.application.face_lower_outer_auxiliary import (
    BuildFaceLowerOuterAuxiliary, FaceLowerOuterAuxiliaryHost,
)


class FaceEyeLidRigHost(FaceLowerOuterAuxiliaryHost, Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_face_eye_lid_preparation(self) -> FaceEyeLidPreparationInput: ...
    def mirror_right_eye_fit_to_left(self, mesh: str) -> dict: ...
    def build_prepared_face_eye_lids(self, mode: FaceEyeLidBuildMode) -> dict: ...


class BuildFaceEyeLids:
    def __init__(self, host: FaceEyeLidRigHost) -> None:
        self.host = host

    def execute(self, *, simpler_eyelid: bool = False) -> dict:
        mode = plan_face_eye_lid_build_mode(simpler_eyelid)
        plan = plan_face_eye_lid_preparation(
            self.host.capture_face_eye_lid_preparation())
        with self.host.transaction("建立双侧眼睑与 Skin"):
            if plan.mirror_left_fit:
                assert plan.left_eye_mesh is not None
                mirror = self.host.mirror_right_eye_fit_to_left(
                    plan.left_eye_mesh)
            else:
                mirror = None
            result = self.host.build_prepared_face_eye_lids(mode)
            if mode.simpler_eyelid:
                auxiliary = BuildFaceLowerOuterAuxiliary(self.host)
                built = []
                for side in ("R", "L"):
                    auxiliary_plan = auxiliary.plan(
                        side, simpler_eyelid=True)
                    if auxiliary_plan is None:
                        raise RuntimeError("简化眼睑缺少眼下外围辅助计划")
                    auxiliary.apply_in_transaction(auxiliary_plan)
                    built.append(auxiliary_plan.joint_name)
                result["lower_outer_auxiliaries"] = tuple(built)
            if mirror is not None:
                result["symmetric_mirror"] = mirror
            if (len(result["controls"]) != mode.expected_arc_controls
                    or len(result["joints"]) < mode.minimum_segment_joints
                    or not all(result["area_vertices"].values())):
                raise RuntimeError("眼睑绑定写后读回不完整")
        return result
