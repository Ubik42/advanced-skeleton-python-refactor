"""Build Inbetween Part FK receivers through a DCC host boundary."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_inbetween_fk_anchor import InbetweenFkAnchorPlan
from adv_py.core.fit_inbetween_fk_parts import (
    InbetweenFkPartSpec, InbetweenFkPartsPlan,
    plan_inbetween_fk_parts,
)
from adv_py.core.fit_part import FitPartJointSpec


class InbetweenFkPartsHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_inbetween_fk_parts(
        self, plan: InbetweenFkPartsPlan
    ) -> None: ...

    def create_inbetween_fk_part(
        self, plan: InbetweenFkPartsPlan,
        part: InbetweenFkPartSpec,
    ) -> None: ...

    def capture_inbetween_fk_part_receiver(
        self, plan: InbetweenFkPartsPlan,
        part: InbetweenFkPartSpec,
    ) -> str | None: ...

    def connect_inbetween_fk_visibility(
        self, plan: InbetweenFkPartsPlan
    ) -> None: ...

    def capture_inbetween_fk_visibility(
        self, plan: InbetweenFkPartsPlan
    ) -> bool: ...


class BuildInbetweenFkParts:
    def __init__(self, host: InbetweenFkPartsHost) -> None:
        self._host = host

    def apply(
        self, anchor: InbetweenFkAnchorPlan,
        body_parts: tuple[FitPartJointSpec, ...], *,
        fk_system_path: str,
        radius: float,
    ) -> InbetweenFkPartsPlan:
        plan = plan_inbetween_fk_parts(
            anchor, body_parts, fk_system_path=fk_system_path,
            radius=radius)
        self._host.preflight_inbetween_fk_parts(plan)
        with self._host.transaction("构建 Inbetween Part FK 接收层"):
            for part in plan.parts:
                self._host.create_inbetween_fk_part(plan, part)
            for part in plan.parts:
                if (self._host.capture_inbetween_fk_part_receiver(plan, part)
                        != part.receiver_plug):
                    raise RuntimeError("Inbetween Part FK 接收端不完整："
                                       + part.part_name)
            self._host.connect_inbetween_fk_visibility(plan)
            if not self._host.capture_inbetween_fk_visibility(plan):
                raise RuntimeError("Inbetween Part FK 显示通道不完整")
        return plan
