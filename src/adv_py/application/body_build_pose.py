"""Restore the registered Body character to its recorded build pose."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_build_pose import BodyBuildPosePlan


class BodyBuildPoseHost(Protocol):
    def read_body_build_pose(self) -> BodyBuildPosePlan: ...
    def preflight_body_build_pose(self, plan: BodyBuildPosePlan) -> None: ...
    def apply_body_build_pose(self, plan: BodyBuildPosePlan) -> None: ...
    def capture_body_build_pose_values(
        self, plan: BodyBuildPosePlan,
    ) -> tuple[float, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class GoToBodyBuildPose:
    def __init__(self, host: BodyBuildPoseHost) -> None:
        self._host = host

    def apply(self) -> int:
        plan = self._host.read_body_build_pose()
        self._host.preflight_body_build_pose(plan)
        with self._host.transaction("返回 Body 构建姿态"):
            self._host.apply_body_build_pose(plan)
            actual = self._host.capture_body_build_pose_values(plan)
            if (len(actual) != len(plan.values)
                    or any(abs(value - item.value) > 1e-5
                           for value, item in zip(actual, plan.values))):
                raise RuntimeError("Body 构建姿态写后读回不一致")
        return len(plan.values)
