"""Create a Fit Part twist graph from explicit rig rotation sources."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_part_twist import (
    FitPartTwistSource, FitPartTwistStep, plan_fit_part_twist,
)


class FitPartTwistHost(Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def preflight_fit_part_twist_step(self, step: FitPartTwistStep) -> None: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_fit_part_twist_step(self, step: FitPartTwistStep) -> None: ...

    def capture_fit_part_twist_output(self, part_name: str) -> str | None: ...


class BuildFitPartTwistDrivers:
    def __init__(self, host: FitPartTwistHost) -> None:
        self._host = host

    def apply(
        self,
        parts: tuple[FitPartJointSpec, ...],
        sources: tuple[FitPartTwistSource, ...],
    ) -> tuple[FitPartTwistStep, ...]:
        steps = plan_fit_part_twist(parts, sources)
        for step in steps:
            self._host.preflight_fit_part_twist_step(step)
            names = (step.amount_node, step.target_node,
                     step.difference_node)
            if step.up_amount_node:
                names += (step.up_amount_node,)
            for name in names:
                if self._host.find_name_collisions(name):
                    raise ValueError("Fit Part 扭转节点名称冲突：" + name)
        with self._host.transaction("构建 Fit Part 扭转驱动"):
            for step in steps:
                self._host.create_fit_part_twist_step(step)
            for step in steps:
                if self._host.capture_fit_part_twist_output(
                        step.part_name) != step.output_plug:
                    raise RuntimeError("Fit Part 扭转输出连接不一致："
                                       + step.part_name)
        return steps
