"""Connect a single Inbetween FKX source to each final Body Part."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_inbetween_fk_body_driver import (
    InbetweenFkBodyDriverPlan, InbetweenFkBodyDriverSpec,
    plan_inbetween_fk_body_drivers,
)
from adv_py.core.fit_inbetween_fk_parts import InbetweenFkPartsPlan


class InbetweenFkBodyDriverHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_inbetween_fk_body_drivers(
        self, plan: InbetweenFkBodyDriverPlan,
    ) -> None: ...
    def create_inbetween_fk_body_driver(
        self, plan: InbetweenFkBodyDriverPlan,
        part: InbetweenFkBodyDriverSpec,
    ) -> None: ...
    def capture_inbetween_fk_body_driver(
        self, plan: InbetweenFkBodyDriverPlan,
        part: InbetweenFkBodyDriverSpec,
    ) -> bool: ...


class BuildInbetweenFkBodyDrivers:
    def __init__(self, host: InbetweenFkBodyDriverHost) -> None:
        self._host = host

    def apply(self, fk: InbetweenFkPartsPlan) -> InbetweenFkBodyDriverPlan:
        plan = plan_inbetween_fk_body_drivers(fk)
        self._host.preflight_inbetween_fk_body_drivers(plan)
        with self._host.transaction("连接 Inbetween Body FK"):
            for part in plan.parts:
                self._host.create_inbetween_fk_body_driver(plan, part)
            for part in plan.parts:
                if not self._host.capture_inbetween_fk_body_driver(plan, part):
                    raise RuntimeError("Inbetween Body FK 驱动不完整："
                                       + part.body_part_name)
        return plan
