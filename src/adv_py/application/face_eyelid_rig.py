"""Coordinate bilateral Fit preparation and the eyelid scene build."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.face_eyelid_build_preparation import (
    FaceEyeLidPreparationInput, plan_face_eye_lid_preparation,
)


class FaceEyeLidRigHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_face_eye_lid_preparation(self) -> FaceEyeLidPreparationInput: ...
    def mirror_right_eye_fit_to_left(self, mesh: str) -> dict: ...
    def build_prepared_face_eye_lids(self) -> dict: ...


class BuildFaceEyeLids:
    def __init__(self, host: FaceEyeLidRigHost) -> None:
        self.host = host

    def execute(self) -> dict:
        plan = plan_face_eye_lid_preparation(
            self.host.capture_face_eye_lid_preparation())
        with self.host.transaction("建立双侧眼睑与 Skin"):
            if plan.mirror_left_fit:
                assert plan.left_eye_mesh is not None
                mirror = self.host.mirror_right_eye_fit_to_left(
                    plan.left_eye_mesh)
            else:
                mirror = None
            result = self.host.build_prepared_face_eye_lids()
            if mirror is not None:
                result["symmetric_mirror"] = mirror
            if (len(result["controls"]) != 8
                    or len(result["joints"]) < 16
                    or not all(result["area_vertices"].values())):
                raise RuntimeError("眼睑绑定写后读回不完整")
        return result
