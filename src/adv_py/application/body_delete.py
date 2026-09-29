"""Remove an AdvancedSkeleton Body build while keeping its Fit source."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_delete import BodyDeletePlan
from adv_py.core.face_delete import FaceDeletePlan


class BodyDeleteHost(Protocol):
    def plan_delete_body_advanced(self, *,
                                  face_will_be_deleted: bool = False
                                  ) -> BodyDeletePlan | None: ...
    def delete_body_advanced(self, plan: BodyDeletePlan) -> None: ...
    def plan_delete_face_advanced(self, *,
                                  keep_build_pose: bool = False
                                  ) -> FaceDeletePlan | None: ...
    def delete_face_advanced(self, plan: FaceDeletePlan) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class DeleteBodyAdvanced:
    def __init__(self, host: BodyDeleteHost) -> None:
        self._host = host

    def apply(self) -> bool:
        face = self._host.plan_delete_face_advanced()
        plan = self._host.plan_delete_body_advanced(
            face_will_be_deleted=face is not None)
        if plan is None:
            return False
        if plan.group is None:
            return False
        with self._host.transaction("删除 Body AdvancedSkeleton，保留 Fit"):
            if face is not None:
                self._host.delete_face_advanced(face)
            self._host.delete_body_advanced(plan)
        return True
