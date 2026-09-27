"""Connect the resolved Body segment scale to non-OPM Fit Part joints."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_part_scale import FitPartScaleStep, plan_fit_part_scale


class FitPartScaleHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_fit_part_scale(self, step: FitPartScaleStep) -> None: ...

    def connect_fit_part_scale(self, step: FitPartScaleStep) -> None: ...

    def capture_fit_part_scale_source(
        self, step: FitPartScaleStep
    ) -> str | None: ...


class BuildFitPartScaleDrivers:
    def __init__(self, host: FitPartScaleHost) -> None:
        self._host = host

    def apply(
        self, parts: tuple[FitPartJointSpec, ...]
    ) -> tuple[FitPartScaleStep, ...]:
        steps = plan_fit_part_scale(parts)
        for step in steps:
            self._host.preflight_fit_part_scale(step)
        with self._host.transaction("构建 Fit Part 缩放驱动"):
            for step in steps:
                self._host.connect_fit_part_scale(step)
            for step in steps:
                if self._host.capture_fit_part_scale_source(step) != step.source_plug:
                    raise RuntimeError("Fit Part 缩放输出连接不一致：" + step.part_name)
        return steps
