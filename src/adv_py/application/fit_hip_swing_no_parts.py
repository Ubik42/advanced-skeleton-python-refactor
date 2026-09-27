"""Host boundary for the Root HipSwinger branch without Inbetween Part."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_hip_swing_no_parts import (
    HipSwingNoPartsPlan, HipSwingNoPartsTopology,
    plan_hip_swing_no_parts,
)
from adv_py.core.fit_inbetween_hip_swing import HipSwingFitSelection


class HipSwingNoPartsHost(Protocol):
    """Create aligned transforms, the Root FKX constraint and matrix links.

    The host must keep the bind pose, disable translate/scale/shear on the
    rotation-only pickMatrix, and verify both leg-lock consumers after write.
    """
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_hip_swing_no_parts(
        self, plan: HipSwingNoPartsPlan,
    ) -> None: ...
    def create_hip_swing_no_parts(
        self, plan: HipSwingNoPartsPlan,
    ) -> None: ...
    def capture_hip_swing_no_parts(
        self, plan: HipSwingNoPartsPlan,
    ) -> bool: ...


class BuildHipSwingNoParts:
    def __init__(self, host: HipSwingNoPartsHost) -> None:
        self._host = host

    def apply(self, selection: HipSwingFitSelection,
              topology: HipSwingNoPartsTopology, *,
              radius: float,
              root_profile: FitDeformProfile) -> HipSwingNoPartsPlan:
        plan = plan_hip_swing_no_parts(
            selection, topology, radius=radius,
            root_profile=root_profile)
        self._host.preflight_hip_swing_no_parts(plan)
        with self._host.transaction("构建无分段 Root HipSwinger"):
            self._host.create_hip_swing_no_parts(plan)
            if not self._host.capture_hip_swing_no_parts(plan):
                raise RuntimeError("无分段 Root HipSwinger 图不完整")
        return plan
