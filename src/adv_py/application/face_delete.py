"""Delete a generated FaceSetup while retaining its Fit and Skin clusters."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.face_delete import FaceDeletePlan


class FaceDeleteHost(Protocol):
    def plan_delete_face_advanced(self, *,
                                  keep_build_pose: bool = False
                                  ) -> FaceDeletePlan | None: ...
    def delete_face_advanced(self, plan: FaceDeletePlan) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class DeleteFaceAdvanced:
    def __init__(self, host: FaceDeleteHost) -> None:
        self._host = host

    def apply(self, *, keep_build_pose: bool = False) -> bool:
        plan = self._host.plan_delete_face_advanced(
            keep_build_pose=keep_build_pose)
        if plan is None:
            return False
        with self._host.transaction("删除 FaceSetup，保留 Face Fit 与 Skin"):
            self._host.delete_face_advanced(plan)
        return True
