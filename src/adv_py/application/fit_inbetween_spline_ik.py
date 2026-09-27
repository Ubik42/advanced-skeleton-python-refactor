"""Build Spline Part IK sources without changing the spline solver chain."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_inbetween_ik_parts import InbetweenIkPartsPlan
from adv_py.core.fit_inbetween_spline_ik import (
    InbetweenSplineIkPlan, plan_inbetween_spline_ik,
)


class InbetweenSplineIkHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_inbetween_spline_ik(self, plan: InbetweenSplineIkPlan) -> None: ...
    def create_inbetween_spline_ik(self, plan: InbetweenSplineIkPlan) -> None: ...
    def capture_inbetween_spline_ik(self, plan: InbetweenSplineIkPlan) -> bool: ...


class BuildInbetweenSplineIk:
    def __init__(self, host: InbetweenSplineIkHost) -> None:
        self._host = host

    def apply(self, body_parts: tuple[FitPartJointSpec, ...], *,
              root_path: str, start_output_path: str,
              end_output_path: str) -> InbetweenIkPartsPlan:
        plan = plan_inbetween_spline_ik(
            body_parts, root_path=root_path,
            start_output_path=start_output_path,
            end_output_path=end_output_path)
        self._host.preflight_inbetween_spline_ik(plan)
        with self._host.transaction("构建 Spline Inbetween IK 来源"):
            self._host.create_inbetween_spline_ik(plan)
            if not self._host.capture_inbetween_spline_ik(plan):
                raise RuntimeError("Spline Inbetween IK 输出不完整")
        return plan.parts
