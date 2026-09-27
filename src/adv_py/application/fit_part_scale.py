"""Connect non-OPM Fit Part scale to resolved body or limb controls."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_part_scale import (
    FitPartLimbScaleChain, FitPartScalePlan, FitPartScaleStep,
    plan_fit_part_scale,
)


class FitPartScaleHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_fit_part_scale(self, step: FitPartScaleStep) -> None: ...

    def connect_fit_part_scale(self, step: FitPartScaleStep) -> None: ...

    def capture_fit_part_scale_source(
        self, step: FitPartScaleStep
    ) -> str | None: ...

    def preflight_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> None: ...

    def connect_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> None: ...

    def capture_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> tuple[str | None, ...]: ...


class BuildFitPartScaleDrivers:
    def __init__(self, host: FitPartScaleHost) -> None:
        self._host = host

    def apply(
        self, parts: tuple[FitPartJointSpec, ...]
    ) -> FitPartScalePlan:
        plan = plan_fit_part_scale(parts)
        for step in plan.direct:
            self._host.preflight_fit_part_scale(step)
        for chain in plan.limbs:
            self._host.preflight_fit_part_limb_scale(chain)
        with self._host.transaction("构建 Fit Part 缩放驱动"):
            for step in plan.direct:
                self._host.connect_fit_part_scale(step)
            for chain in plan.limbs:
                self._host.connect_fit_part_limb_scale(chain)
            for step in plan.direct:
                if self._host.capture_fit_part_scale_source(step) != step.source_plug:
                    raise RuntimeError("Fit Part 缩放输出连接不一致：" + step.part_name)
            for chain in plan.limbs:
                if self._host.capture_fit_part_limb_scale(chain) != (
                        chain.output_plug,) * len(chain.part_names):
                    raise RuntimeError("Fit Part 四肢缩放连接不一致："
                                       + chain.start_body_name)
        return plan
