"""Choose the bilateral Fit preparation required by an eyelid build."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_settings import FitSkeletonValidationError


@dataclass(frozen=True, slots=True)
class FaceEyeLidPreparationInput:
    symmetric: bool
    left_fit_complete: bool
    eyes_only: bool
    left_eye_mesh: str | None


@dataclass(frozen=True, slots=True)
class FaceEyeLidPreparationPlan:
    mirror_left_fit: bool
    left_eye_mesh: str | None


def plan_face_eye_lid_preparation(
    source: FaceEyeLidPreparationInput,
) -> FaceEyeLidPreparationPlan:
    if not all(isinstance(value, bool) for value in (
            source.symmetric, source.left_fit_complete, source.eyes_only)):
        raise FitSkeletonValidationError("眼睑 Fit 准备状态必须是布尔值")
    mirror = source.symmetric and not source.left_fit_complete
    if mirror and not source.eyes_only:
        raise FitSkeletonValidationError(
            "当前眼睑构建阶段需要 Skip Above+Below Eyes")
    if mirror and not source.left_eye_mesh:
        raise FitSkeletonValidationError(
            "先从 Face / Pre 构建双眼控制与蒙皮，再建立眼睑")
    return FaceEyeLidPreparationPlan(
        mirror, source.left_eye_mesh if mirror else None)
