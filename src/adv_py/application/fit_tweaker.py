"""Build Fit Tweaker controls and verify their neutral pose."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_tweaker import (
    FitTweakerPlan, FitTweakerSourceState, FitTweakerSpec,
)


class FitTweakerHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_fit_tweakers(
        self, plan: FitTweakerPlan,
    ) -> tuple[FitTweakerSourceState, ...]: ...

    def create_fit_tweaker_system(self, plan: FitTweakerPlan) -> None: ...

    def capture_fit_tweaker_system(self, plan: FitTweakerPlan) -> bool: ...

    def create_fit_tweaker(
        self, plan: FitTweakerPlan, spec: FitTweakerSpec,
        state: FitTweakerSourceState,
    ) -> None: ...

    def capture_fit_tweaker(
        self, plan: FitTweakerPlan, spec: FitTweakerSpec,
        state: FitTweakerSourceState,
    ) -> bool: ...


class BuildFitTweakers:
    def __init__(self, host: FitTweakerHost) -> None:
        self._host = host

    def apply(self, plan: FitTweakerPlan) -> FitTweakerPlan:
        if not plan.controls:
            return plan
        states = self._host.preflight_fit_tweakers(plan)
        if len(states) != len(plan.controls):
            raise RuntimeError("Tweaker 目标预检数量不一致")
        with self._host.transaction("构建 Fit Tweaker 控制层"):
            self._host.create_fit_tweaker_system(plan)
            if not self._host.capture_fit_tweaker_system(plan):
                raise RuntimeError("TweakerSystem 显示通道读回不一致")
            for spec, state in zip(plan.controls, states):
                self._host.create_fit_tweaker(plan, spec, state)
            for spec, state in zip(plan.controls, states):
                if not self._host.capture_fit_tweaker(plan, spec, state):
                    raise RuntimeError("Tweaker 构建读回不一致："
                                       + spec.target_path)
        return plan
