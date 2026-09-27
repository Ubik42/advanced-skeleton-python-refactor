"""Connect the Inbetween FK bias curves through a DCC host boundary."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_inbetween_bias import (
    InbetweenBiasPlan, plan_inbetween_bias,
)


class InbetweenBiasHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_inbetween_bias(self, plan: InbetweenBiasPlan) -> None: ...

    def create_inbetween_bias(self, plan: InbetweenBiasPlan) -> None: ...

    def capture_inbetween_bias_outputs(
        self, plan: InbetweenBiasPlan
    ) -> tuple[str | None, ...]: ...


class BuildInbetweenBias:
    def __init__(self, host: InbetweenBiasHost) -> None:
        self._host = host

    def apply(
        self, start_body_name: str,
        part_names: tuple[str, ...],
        control_plug: str,
    ) -> InbetweenBiasPlan:
        plan = plan_inbetween_bias(
            start_body_name, part_names, control_plug)
        self._host.preflight_inbetween_bias(plan)
        with self._host.transaction("构建 Inbetween FK Bias"):
            self._host.create_inbetween_bias(plan)
            if self._host.capture_inbetween_bias_outputs(plan) != (
                    plan.start_curve.name + ".outValue",
                    plan.mid_curve.name + ".outValue",
                    plan.end_curve.name + ".outValue"):
                raise RuntimeError("Inbetween FK Bias 输出不完整："
                                   + start_body_name)
        return plan
