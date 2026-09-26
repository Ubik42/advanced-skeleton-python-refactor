"""Application boundary for controller local-axis edits."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.control_orientation import (
    ControlAxis, ControlOrientationPlan, ControlOrientationState,
    plan_control_orientation_axis,
)


class ControlOrientationHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_control_orientations(
        self, controls: tuple[str, ...]
    ) -> tuple[ControlOrientationState, ...]: ...
    def apply_control_orientation(self, state: ControlOrientationState) -> None: ...


@dataclass(frozen=True, slots=True)
class ControlOrientationResult:
    plan: ControlOrientationPlan
    verified: tuple[ControlOrientationState, ...]


class SetControlOrientationAxis:
    def __init__(self, host: ControlOrientationHost) -> None:
        self._host = host

    def apply(self, controls: tuple[str, ...], primary: ControlAxis | str,
              secondary: ControlAxis | str) -> ControlOrientationResult:
        plan = plan_control_orientation_axis(
            self._host.capture_control_orientations(controls),
            primary, secondary)
        with self._host.transaction(
                f"设置 {len(plan.changes)} 个控制器的 Primary/Secondary Axis"):
            for change in plan.changes:
                self._host.apply_control_orientation(change.after)
            verified = self._host.capture_control_orientations(
                tuple(change.after.control for change in plan.changes))
            self._verify(plan, verified)
        return ControlOrientationResult(plan, verified)

    @staticmethod
    def _verify(plan, actual):
        if len(actual) != len(plan.changes):
            raise RuntimeError("控制器方向复检失败：数量变化")
        for change, found in zip(plan.changes, actual):
            expected = change.after
            if (found.control != expected.control
                    or found.primary_axis != expected.primary_axis
                    or found.secondary_axis != expected.secondary_axis
                    or any(abs(a - b) > 1e-5 for a, b in
                           zip(found.world_matrix, expected.world_matrix))):
                raise RuntimeError("控制器方向复检失败：坐标轴或世界矩阵不一致")
