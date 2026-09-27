"""Build Inbetween IKX segment sources through a DCC host."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_inbetween_ik_parts import (
    InbetweenIkPartSpec, InbetweenIkPartsPlan,
    plan_inbetween_ik_parts,
)
from adv_py.core.fit_part import FitPartJointSpec


class InbetweenIkPartsHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_inbetween_ik_parts(
        self, plan: InbetweenIkPartsPlan
    ) -> None: ...

    def create_inbetween_ik_part(
        self, plan: InbetweenIkPartsPlan,
        part: InbetweenIkPartSpec,
    ) -> None: ...

    def capture_inbetween_ik_part(
        self, plan: InbetweenIkPartsPlan,
        part: InbetweenIkPartSpec,
    ) -> bool: ...


class BuildInbetweenIkParts:
    def __init__(self, host: InbetweenIkPartsHost) -> None:
        self._host = host

    def apply(
        self, body_parts: tuple[FitPartJointSpec, ...], *,
        start_ik_driver: str,
        end_ik_driver: str,
    ) -> InbetweenIkPartsPlan:
        plan = plan_inbetween_ik_parts(
            body_parts, start_ik_driver=start_ik_driver,
            end_ik_driver=end_ik_driver)
        self._host.preflight_inbetween_ik_parts(plan)
        with self._host.transaction("构建 Inbetween IK 分段"):
            for part in plan.parts:
                self._host.create_inbetween_ik_part(plan, part)
            for part in plan.parts:
                if not self._host.capture_inbetween_ik_part(plan, part):
                    raise RuntimeError("Inbetween IK 分段输出不完整："
                                       + part.body_part_name)
        return plan
