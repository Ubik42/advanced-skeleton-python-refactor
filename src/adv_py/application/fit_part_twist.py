"""Create a Fit Part twist graph from explicit rig rotation sources."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_part_twist import (
    FitPartRotationInput, FitPartTwistProjection, FitPartTwistSource,
    FitPartTwistStep, plan_fit_part_twist, plan_fit_part_twist_projections,
)


class FitPartTwistHost(Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def preflight_fit_part_twist_step(self, step: FitPartTwistStep) -> None: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def create_fit_part_twist_step(self, step: FitPartTwistStep) -> None: ...

    def capture_fit_part_twist_output(self, part_name: str) -> str | None: ...

    def preflight_fit_part_twist_projection(
        self, projection: FitPartTwistProjection
    ) -> None: ...

    def create_fit_part_twist_projection(
        self, projection: FitPartTwistProjection
    ) -> None: ...

    def capture_fit_part_projection_output(
        self, projection: FitPartTwistProjection
    ) -> str | None: ...


class PrepareFitPartTwistSources:
    def __init__(self, host: FitPartTwistHost) -> None:
        self._host = host

    def apply(self, inputs: tuple[FitPartRotationInput, ...]
              ) -> tuple[FitPartTwistSource, ...]:
        projections = plan_fit_part_twist_projections(inputs)
        for projection in projections:
            self._host.preflight_fit_part_twist_projection(projection)
            names = (projection.compose_name, projection.decompose_name,
                     projection.project_name)
            names += tuple(name for name in (
                projection.ik_compose_name,
                projection.ik_decompose_name,
                projection.ik_project_name,
                projection.blend_name) if name)
            for name in names:
                if self._host.find_name_collisions(name):
                    raise ValueError("Fit Part 投影节点名称冲突：" + name)
        with self._host.transaction("构建 Fit Part 扭转来源"):
            for projection in projections:
                self._host.create_fit_part_twist_projection(projection)
            for projection in projections:
                if (self._host.capture_fit_part_projection_output(projection)
                        != projection.output_plug):
                    raise RuntimeError("Fit Part 扭转投影输出不一致："
                                       + projection.input.start_body)
        return tuple(projection.source() for projection in projections)


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
