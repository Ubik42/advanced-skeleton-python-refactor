"""Join Inbetween FK, IK and Body Part stages in one DCC transaction."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_inbetween_body_driver import InbetweenBodyDriverPlan
from adv_py.core.fit_inbetween_ik_parts import InbetweenIkPartsPlan
from adv_py.core.fit_inbetween_fk_rewire import InbetweenFkRewirePlan

from .fit_inbetween_body_driver import (
    BuildInbetweenBodyDrivers, InbetweenBodyDriverHost,
)
from .fit_inbetween_fk_graph import (
    BuildInbetweenFkGraph, InbetweenFkGraphHost,
    InbetweenFkGraphResult,
)
from .fit_inbetween_fk_rewire import (
    BuildInbetweenFkRewire, InbetweenFkRewireHost,
)
from .fit_inbetween_ik_parts import (
    BuildInbetweenIkParts, InbetweenIkPartsHost,
)


class InbetweenLimbSegmentHost(
    InbetweenFkGraphHost, InbetweenIkPartsHost,
    InbetweenBodyDriverHost, InbetweenFkRewireHost, Protocol,
):
    pass


class _WithinTransaction:
    def __init__(self, host: InbetweenLimbSegmentHost) -> None:
        self._host = host

    def __getattr__(self, name: str):
        return getattr(self._host, name)

    @contextmanager
    def transaction(self, label: str):
        del label
        yield


@dataclass(frozen=True, slots=True)
class InbetweenLimbSegmentResult:
    fk: InbetweenFkGraphResult
    rewire: InbetweenFkRewirePlan
    ik: InbetweenIkPartsPlan
    body: InbetweenBodyDriverPlan


class BuildInbetweenLimbSegment:
    """Build a segment after Body Parts and standard Rig exist."""

    def __init__(self, host: InbetweenLimbSegmentHost) -> None:
        self._host = host

    def apply(
        self, body_parts: tuple[FitPartJointSpec, ...], *,
        fk_offset_path: str,
        fk_control_path: str,
        fk_system_path: str,
        start_fk_driver_path: str,
        start_fk_constraint_name: str,
        downstream_fk_offset_path: str,
        start_ik_driver: str,
        end_ik_driver: str,
        fk_weight_plug: str,
        ik_weight_plug: str,
        rotate_order: int,
        part_control_radius: float,
    ) -> InbetweenLimbSegmentResult:
        if not body_parts:
            raise ValueError("Inbetween 四肢段缺少 Body Part")
        with self._host.transaction("构建 Inbetween 四肢段"):
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
            ik = BuildInbetweenIkParts(joined).apply(
                body_parts, start_ik_driver=start_ik_driver,
                end_ik_driver=end_ik_driver)
            if fk.parts is None:
                raise RuntimeError("Inbetween FK 缺少 Part 接收层")
            body = BuildInbetweenBodyDrivers(joined).apply(
                fk.parts, ik, fk_weight_plug=fk_weight_plug,
                ik_weight_plug=ik_weight_plug)
        return InbetweenLimbSegmentResult(fk, rewire, ik, body)
