"""Copy control curve CVs into existing ADV Sub/Extra controller layers."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.control_curve_variants import (
    ControlCurveVariantState, audit_control_curve_variants,
    plan_control_curve_variants,
)


class ControlCurveVariantHost(Protocol):
    def capture_control_curve_variants(
        self, controls: tuple[str, ...], variant: str,
    ) -> tuple[ControlCurveVariantState, ...]: ...
    def set_control_curve_world_points(
        self, shape: str, points: tuple[tuple[float, float, float], ...],
    ) -> None: ...
    def transaction(self, label: str): ...


class CopyControlCurvesToVariants:
    def __init__(self, host: ControlCurveVariantHost) -> None:
        self._host = host

    def apply(self, controls: tuple[str, ...], variant: str) -> int:
        before = self._host.capture_control_curve_variants(
            controls, variant)
        plan = plan_control_curve_variants(variant, before)
        with self._host.transaction("复制控制曲线到 " + variant):
            if self._host.capture_control_curve_variants(
                    controls, variant) != before:
                raise RuntimeError("控制曲线在执行前发生变化")
            for item, desired in zip(plan.before, plan.desired):
                self._host.set_control_curve_world_points(
                    item.target_shape, desired)
            after = self._host.capture_control_curve_variants(
                controls, variant)
            issues = audit_control_curve_variants(plan, after)
            if issues:
                raise RuntimeError("；".join(issues))
        return len(plan.before)
