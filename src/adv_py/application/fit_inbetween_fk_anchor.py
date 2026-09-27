"""Materialize Inbetween FK anchor nodes through a DCC host boundary."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_inbetween_fk_anchor import (
    InbetweenFkAnchorPlan, plan_inbetween_fk_anchor,
)


class InbetweenFkAnchorHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_inbetween_fk_anchor(
        self, plan: InbetweenFkAnchorPlan
    ) -> None: ...

    def create_inbetween_fk_anchor(
        self, plan: InbetweenFkAnchorPlan
    ) -> None: ...

    def capture_inbetween_fk_anchor(
        self, plan: InbetweenFkAnchorPlan
    ) -> tuple[str | None, ...]: ...


class BuildInbetweenFkAnchor:
    def __init__(self, host: InbetweenFkAnchorHost) -> None:
        self._host = host

    def apply(
        self, start_body_name: str, *,
        fk_offset_path: str,
        fk_control_path: str,
        rotate_order: int,
    ) -> InbetweenFkAnchorPlan:
        plan = plan_inbetween_fk_anchor(
            start_body_name, fk_offset_path=fk_offset_path,
            fk_control_path=fk_control_path, rotate_order=rotate_order)
        self._host.preflight_inbetween_fk_anchor(plan)
        with self._host.transaction("构建 Inbetween FK 起点层"):
            self._host.create_inbetween_fk_anchor(plan)
            if self._host.capture_inbetween_fk_anchor(plan) != (
                    plan.base_world_plug, plan.target_world_plug,
                    plan.parent_inverse_plug, plan.start_fkx_opm_plug):
                raise RuntimeError("Inbetween FK 起点层不完整："
                                   + plan.start_body_name)
        return plan
