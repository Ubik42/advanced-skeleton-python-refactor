"""Join FK-only Inbetween stages for a segment without an IK mechanism."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_inbetween_fk_body_driver import InbetweenFkBodyDriverPlan
from adv_py.core.fit_inbetween_fk_rewire import InbetweenFkRewirePlan

from .fit_inbetween_fk_body_driver import (
    BuildInbetweenFkBodyDrivers, InbetweenFkBodyDriverHost,
)
from .fit_inbetween_fk_graph import (
    BuildInbetweenFkGraph, InbetweenFkGraphHost, InbetweenFkGraphResult,
)
from .fit_inbetween_fk_rewire import (
    BuildInbetweenFkRewire, InbetweenFkRewireHost,
)


class InbetweenFkSegmentHost(
    InbetweenFkGraphHost, InbetweenFkRewireHost,
    InbetweenFkBodyDriverHost, Protocol,
):
    pass


class _WithinTransaction:
    def __init__(self, host: InbetweenFkSegmentHost) -> None:
        self._host = host

    def __getattr__(self, name: str):
        return getattr(self._host, name)

    @contextmanager
    def transaction(self, label: str):
        del label
        yield


@dataclass(frozen=True, slots=True)
class InbetweenFkSegmentResult:
    fk: InbetweenFkGraphResult
    rewire: InbetweenFkRewirePlan
    body: InbetweenFkBodyDriverPlan


class BuildInbetweenFkSegment:
    def __init__(self, host: InbetweenFkSegmentHost) -> None:
        self._host = host

    def apply(
        self, body_parts: tuple[FitPartJointSpec, ...], *,
        fk_offset_path: str,
        fk_control_path: str,
        fk_system_path: str,
        start_fk_driver_path: str,
        start_fk_constraint_name: str,
        downstream_fk_offset_path: str,
        rotate_order: int,
        part_control_radius: float,
    ) -> InbetweenFkSegmentResult:
        if not body_parts:
            raise ValueError("Inbetween FK 段缺少 Body Part")
        with self._host.transaction("构建 Inbetween FK 段"):
            joined = _WithinTransaction(self._host)
            fk = BuildInbetweenFkGraph(joined).apply_with_parts(
                body_parts[0].start_body_name, body_parts,
                fk_offset_path=fk_offset_path,
                fk_control_path=fk_control_path,
                fk_system_path=fk_system_path,
                rotate_order=rotate_order,
                part_control_radius=part_control_radius)
            rewire = BuildInbetweenFkRewire(joined).apply(
                fk, start_fk_driver_path=start_fk_driver_path,
                start_fk_constraint_name=start_fk_constraint_name,
                downstream_fk_offset_path=downstream_fk_offset_path)
            if fk.parts is None:
                raise RuntimeError("Inbetween FK 缺少 Part 接收层")
            body = BuildInbetweenFkBodyDrivers(joined).apply(fk.parts)
        return InbetweenFkSegmentResult(fk, rewire, body)
