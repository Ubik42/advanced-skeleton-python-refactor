"""Create an optional Inbetween UnTwister through an explicit host boundary."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_inbetween_untwister import (
    InbetweenUnTwisterPlan, InbetweenUnTwisterStep,
    plan_inbetween_untwister,
)


class InbetweenUnTwisterHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_inbetween_untwister(
        self, plan: InbetweenUnTwisterPlan,
    ) -> None: ...
    def create_inbetween_untwister_source(
        self, plan: InbetweenUnTwisterPlan,
    ) -> None: ...
    def capture_inbetween_untwister_source(
        self, plan: InbetweenUnTwisterPlan,
    ) -> bool: ...
    def create_inbetween_untwister_step(
        self, plan: InbetweenUnTwisterPlan,
        step: InbetweenUnTwisterStep,
    ) -> None: ...
    def capture_inbetween_untwister_step(
        self, plan: InbetweenUnTwisterPlan,
        step: InbetweenUnTwisterStep,
    ) -> bool: ...


class BuildInbetweenUnTwister:
    def __init__(self, host: InbetweenUnTwisterHost) -> None:
        self._host = host

    def apply(
        self, parts: tuple[FitPartJointSpec, ...],
        constraint_names: tuple[str, ...], *,
        end_fk_control_path: str,
        end_fk_offset_path: str,
    ) -> InbetweenUnTwisterPlan:
        plan = plan_inbetween_untwister(
            parts, constraint_names,
            end_fk_control_path=end_fk_control_path,
            end_fk_offset_path=end_fk_offset_path)
        self._host.preflight_inbetween_untwister(plan)
        with self._host.transaction("构建 Inbetween UnTwister"):
            self._host.create_inbetween_untwister_source(plan)
            if not self._host.capture_inbetween_untwister_source(plan):
                raise RuntimeError("Inbetween UnTwister 旋转来源不完整")
            for step in plan.steps:
                self._host.create_inbetween_untwister_step(plan, step)
            for step in plan.steps:
                if not self._host.capture_inbetween_untwister_step(
                        plan, step):
                    raise RuntimeError("Inbetween UnTwister 输出不完整："
                                       + step.part_name)
        return plan
