"""Materialize source matrices for each Inbetween FK segment."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_inbetween_bias import InbetweenBiasPlan
from adv_py.core.fit_inbetween_matrix import (
    InbetweenMatrixDestination, InbetweenMatrixPlan,
    InbetweenMatrixStep, plan_inbetween_matrices,
    plan_inbetween_matrix_destinations,
)


class InbetweenMatrixHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_inbetween_matrices(
        self, plan: InbetweenMatrixPlan
    ) -> None: ...

    def create_inbetween_matrix_step(
        self, plan: InbetweenMatrixPlan,
        step: InbetweenMatrixStep,
    ) -> None: ...

    def capture_inbetween_matrix_output(
        self, step: InbetweenMatrixStep
    ) -> str | None: ...

    def preflight_inbetween_matrix_destinations(
        self, destinations: tuple[InbetweenMatrixDestination, ...]
    ) -> None: ...

    def connect_inbetween_matrix_destination(
        self, destination: InbetweenMatrixDestination
    ) -> None: ...

    def capture_inbetween_matrix_destination(
        self, destination: InbetweenMatrixDestination
    ) -> str | None: ...


class BuildInbetweenMatrices:
    def __init__(self, host: InbetweenMatrixHost) -> None:
        self._host = host

    def apply(
        self, bias: InbetweenBiasPlan, *,
        base_world_plug: str,
        target_world_plug: str,
        parent_inverse_plug: str,
    ) -> InbetweenMatrixPlan:
        plan = plan_inbetween_matrices(
            bias, base_world_plug=base_world_plug,
            target_world_plug=target_world_plug,
            parent_inverse_plug=parent_inverse_plug)
        self._host.preflight_inbetween_matrices(plan)
        with self._host.transaction("构建 Inbetween 矩阵来源"):
            for step in plan.steps:
                self._host.create_inbetween_matrix_step(plan, step)
            for step in plan.steps:
                if (self._host.capture_inbetween_matrix_output(step)
                        != step.output_plug):
                    raise RuntimeError("Inbetween 矩阵输出不完整："
                                       + step.joint_name)
        return plan

    def connect_destinations(
        self, plan: InbetweenMatrixPlan, *,
        start_fkx_opm_plug: str,
        part_fk_matrix_plugs: tuple[str, ...],
    ) -> tuple[InbetweenMatrixDestination, ...]:
        destinations = plan_inbetween_matrix_destinations(
            plan, start_fkx_opm_plug=start_fkx_opm_plug,
            part_fk_matrix_plugs=part_fk_matrix_plugs)
        self._host.preflight_inbetween_matrix_destinations(destinations)
        with self._host.transaction("连接 Inbetween FK 矩阵"):
            for destination in destinations:
                self._host.connect_inbetween_matrix_destination(destination)
            for destination in destinations:
                if (self._host.capture_inbetween_matrix_destination(
                        destination) != destination.source_plug):
                    raise RuntimeError("Inbetween FK 矩阵接收端未连接："
                                       + destination.joint_name)
        return destinations
