"""Restore the Python Face controls from faceBuildPose numeric records."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_build_pose import BodyBuildPosePlan


class FaceBuildPoseHost(Protocol):
    def read_face_build_pose(self) -> BodyBuildPosePlan: ...
    def preflight_face_build_pose(self, plan: BodyBuildPosePlan) -> None: ...
    def apply_face_build_pose(self, plan: BodyBuildPosePlan) -> None: ...
    def capture_face_build_pose_values(
        self, plan: BodyBuildPosePlan,
    ) -> tuple[float, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class GoToFaceBuildPose:
    def __init__(self, host: FaceBuildPoseHost) -> None:
        self._host = host

    def apply(self) -> int:
        plan = self._host.read_face_build_pose()
        self._host.preflight_face_build_pose(plan)
        with self._host.transaction("返回 Face 构建姿态"):
            self._host.apply_face_build_pose(plan)
            actual = self._host.capture_face_build_pose_values(plan)
            if (len(actual) != len(plan.values)
                    or any(abs(value - item.value) > 1e-5
                           for value, item in zip(actual, plan.values))):
                raise RuntimeError("Face 构建姿态写后读回不一致")
        return len(plan.values)
