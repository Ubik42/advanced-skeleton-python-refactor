"""Move the existing limb FK source and next control to Inbetween FKX."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_inbetween_fk_rewire import (
    InbetweenFkRewirePlan, plan_inbetween_fk_rewire,
)

from .fit_inbetween_fk_graph import InbetweenFkGraphResult


class InbetweenFkRewireHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_inbetween_fk_rewire(
        self, plan: InbetweenFkRewirePlan
    ) -> None: ...

    def apply_inbetween_fk_rewire(
        self, plan: InbetweenFkRewirePlan
    ) -> None: ...

    def capture_inbetween_fk_rewire(
        self, plan: InbetweenFkRewirePlan
    ) -> bool: ...


class BuildInbetweenFkRewire:
    def __init__(self, host: InbetweenFkRewireHost) -> None:
        self._host = host

    def apply(
        self, graph: InbetweenFkGraphResult, *,
        start_fk_driver_path: str,
        start_fk_constraint_name: str,
        downstream_fk_offset_path: str,
    ) -> InbetweenFkRewirePlan:
        if graph.parts is None:
            raise ValueError("Inbetween FK 改接缺少 Part 接收层")
        plan = plan_inbetween_fk_rewire(
            graph.anchor, graph.parts,
            start_fk_driver_path=start_fk_driver_path,
            start_fk_constraint_name=start_fk_constraint_name,
            downstream_fk_offset_path=downstream_fk_offset_path)
        self._host.preflight_inbetween_fk_rewire(plan)
        with self._host.transaction("改接 Inbetween FK 链"):
            self._host.apply_inbetween_fk_rewire(plan)
            if not self._host.capture_inbetween_fk_rewire(plan):
                raise RuntimeError("Inbetween FK 链改接不完整")
        return plan
