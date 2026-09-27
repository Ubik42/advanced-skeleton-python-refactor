"""Connect Inbetween FK/IK orientation to final Body Part joints."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_inbetween_body_driver import (
    InbetweenBodyDriverPlan, InbetweenBodyDriverSpec,
    plan_inbetween_body_drivers,
)
from adv_py.core.fit_inbetween_fk_parts import InbetweenFkPartsPlan
from adv_py.core.fit_inbetween_ik_parts import InbetweenIkPartsPlan


class InbetweenBodyDriverHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_inbetween_body_drivers(
        self, plan: InbetweenBodyDriverPlan
    ) -> None: ...

    def create_inbetween_body_driver(
        self, plan: InbetweenBodyDriverPlan,
        part: InbetweenBodyDriverSpec,
    ) -> None: ...

    def capture_inbetween_body_driver(
        self, plan: InbetweenBodyDriverPlan,
        part: InbetweenBodyDriverSpec,
    ) -> bool: ...


class BuildInbetweenBodyDrivers:
    def __init__(self, host: InbetweenBodyDriverHost) -> None:
        self._host = host

    def apply(
        self, fk: InbetweenFkPartsPlan,
        ik: InbetweenIkPartsPlan, *,
        fk_weight_plug: str,
        ik_weight_plug: str,
    ) -> InbetweenBodyDriverPlan:
        plan = plan_inbetween_body_drivers(
            fk, ik, fk_weight_plug=fk_weight_plug,
            ik_weight_plug=ik_weight_plug)
        self._host.preflight_inbetween_body_drivers(plan)
        with self._host.transaction("连接 Inbetween Body FK／IK"):
            for part in plan.parts:
                self._host.create_inbetween_body_driver(plan, part)
            for part in plan.parts:
                if not self._host.capture_inbetween_body_driver(plan, part):
                    raise RuntimeError("Inbetween Body FK／IK 驱动不完整："
                                       + part.body_part_name)
        return plan
