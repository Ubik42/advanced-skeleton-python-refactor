from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_spine import BodySpinePlan, SpineWorldPose, SPINE_MATCH_TOLERANCE, spine_pose_error
from adv_py.core.fit_settings import FitSkeletonValidationError


class BodySpineMatchHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_body_spine_match(self, plan: BodySpinePlan, mode: str) -> float: ...
    def capture_body_spine_pose(self, plan: BodySpinePlan) -> SpineWorldPose: ...
    def match_body_spine(self, plan: BodySpinePlan, mode: str) -> None: ...
    def validate_body_spine(self, plan: BodySpinePlan) -> None: ...


class MatchBodySpine:
    """Match the inactive spine controls at the current time, in one Undo operation."""

    def __init__(self, host: BodySpineMatchHost):
        self._host = host

    def execute(self, plan: BodySpinePlan, mode: str) -> SpineWorldPose:
        value = self._host.preflight_body_spine_match(plan, mode)
        before = self._host.capture_body_spine_pose(plan)
        spine_pose_error(before, before)
        if value == (1.0 if mode == "ik" else 0.0):
            return before
        with self._host.transaction("Match Spine " + mode.upper()):
            if self._host.preflight_body_spine_match(plan, mode) != value:
                raise FitSkeletonValidationError("Spine 匹配输入发生变化")
            if spine_pose_error(before, self._host.capture_body_spine_pose(plan)) > SPINE_MATCH_TOLERANCE:
                raise FitSkeletonValidationError("Spine 匹配前身体姿态发生变化")
            self._host.match_body_spine(plan, mode)
            after = self._host.capture_body_spine_pose(plan)
            if spine_pose_error(before, after) > SPINE_MATCH_TOLERANCE:
                raise RuntimeError("Spine 匹配改变了身体世界姿态，已回滚")
            self._host.validate_body_spine(plan)
        return after
