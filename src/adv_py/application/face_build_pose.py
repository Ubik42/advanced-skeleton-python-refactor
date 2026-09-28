"""Restore the Python Face controls from faceBuildPose numeric records."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_build_pose import (
    BodyBuildPoseOverrides, BodyBuildPosePlan,
    plan_body_build_pose_overrides,
)


class FaceBuildPoseHost(Protocol):
    def read_face_build_pose_base(self) -> BodyBuildPosePlan: ...
    def read_face_build_pose(self) -> BodyBuildPosePlan: ...
    def read_face_build_pose_overrides(self) -> BodyBuildPoseOverrides: ...
    def capture_current_face_build_pose(
        self, base: BodyBuildPosePlan,
    ) -> BodyBuildPosePlan: ...
    def write_face_build_pose_overrides(
        self, overrides: BodyBuildPoseOverrides,
    ) -> None: ...
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


class SetFaceBuildPose:
    def __init__(self, host: FaceBuildPoseHost) -> None:
        self._host = host

    def apply(self) -> int:
        base = self._host.read_face_build_pose_base()
        self._host.preflight_face_build_pose(base)
        current = self._host.capture_current_face_build_pose(base)
        self._host.preflight_face_build_pose(current)
        overrides = plan_body_build_pose_overrides(base, current)
        with self._host.transaction("设置 Face 构建姿态"):
            self._host.write_face_build_pose_overrides(overrides)
            if self._host.read_face_build_pose_overrides() != overrides:
                raise RuntimeError("Face 构建姿态覆盖值写后读回不一致")
        return len(overrides.values)
