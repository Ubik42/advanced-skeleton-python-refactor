"""Build a Root Inbetween HipSwingReverse graph through a host contract."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_inbetween_hip_swing import (
    HipSwingReversePlan, plan_hip_swing_reverse,
)


class HipSwingReverseHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_hip_swing_reverse(self,
                                   plan: HipSwingReversePlan) -> None: ...
    def create_hip_swing_reverse(self,
                                 plan: HipSwingReversePlan) -> None: ...
    def capture_hip_swing_reverse(self,
                                  plan: HipSwingReversePlan) -> bool: ...


class BuildHipSwingReverse:
    def __init__(self, host: HipSwingReverseHost) -> None:
        self._host = host

    def apply(self, parts: tuple[FitPartJointSpec, ...], *,
              start_fk_offset_path: str,
              start_fk_control_path: str,
              end_body_path: str,
              radius: float,
              root_profile: FitDeformProfile) -> HipSwingReversePlan:
        plan = plan_hip_swing_reverse(
            parts, start_fk_offset_path=start_fk_offset_path,
            start_fk_control_path=start_fk_control_path,
            end_body_path=end_body_path, radius=radius,
            root_profile=root_profile)
        self._host.preflight_hip_swing_reverse(plan)
        with self._host.transaction("构建 Root HipSwingReverse"):
            self._host.create_hip_swing_reverse(plan)
            if not self._host.capture_hip_swing_reverse(plan):
                raise RuntimeError("Root HipSwingReverse 图不完整")
        return plan
