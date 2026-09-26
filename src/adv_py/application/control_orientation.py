"""Application boundary for controller local-axis edits."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.control_orientation import (
    ControlAxis, ControlOrientationPlan, ControlOrientationState,
    CustomOrientationPreview, plan_control_orientation_axis,
    plan_custom_control_orientations,
)


class ControlOrientationHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_control_orientations(
        self, controls: tuple[str, ...]
    ) -> tuple[ControlOrientationState, ...]: ...
    def capture_control_curve_world_points(
        self, controls: tuple[str, ...]
    ) -> tuple[tuple[str, tuple[tuple[float, float, float], ...]], ...]: ...
    def apply_control_orientation(self, state: ControlOrientationState) -> None: ...
    def restore_control_curve_world_points(
        self, shapes: tuple[tuple[str, tuple[tuple[float, float, float], ...]], ...]
    ) -> None: ...
    def detach_custom_control_orientations(
        self, states: tuple[ControlOrientationState, ...]
    ) -> tuple[str, ...]: ...
    def capture_custom_control_orientation_previews(
        self,
    ) -> tuple[CustomOrientationPreview, ...]: ...
    def finish_custom_control_orientations(self) -> None: ...
    def read_character_registration(self): ...


@dataclass(frozen=True, slots=True)
class ControlOrientationResult:
    plan: ControlOrientationPlan
    verified: tuple[ControlOrientationState, ...]


class SetControlOrientationAxis:
    def __init__(self, host: ControlOrientationHost) -> None:
        self._host = host

    def apply(self, controls: tuple[str, ...], primary: ControlAxis | str,
              secondary: ControlAxis | str,
              curve_unaffected: bool = False) -> ControlOrientationResult:
        plan = plan_control_orientation_axis(
            self._host.capture_control_orientations(controls),
            primary, secondary, curve_unaffected)
        points = (self._host.capture_control_curve_world_points(controls)
                  if curve_unaffected else ())
        with self._host.transaction(
                f"设置 {len(plan.changes)} 个控制器的 Primary/Secondary Axis"):
            for change in plan.changes:
                self._host.apply_control_orientation(change.after)
            if curve_unaffected:
                self._host.restore_control_curve_world_points(points)
            verified = self._host.capture_control_orientations(
                tuple(change.after.control for change in plan.changes))
            self._verify(plan, verified)
            if curve_unaffected:
                restored = self._host.capture_control_curve_world_points(controls)
                if (len(restored) != len(points) or any(
                        path != expected_path or len(actual) != len(expected)
                        or any(any(abs(a - b) > 1e-5 for a, b in zip(point, old))
                               for point, old in zip(actual, expected))
                        for (path, actual), (expected_path, expected)
                        in zip(restored, points))):
                    raise RuntimeError("Curve Unaffected 世界曲线复检失败")
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
                    or found.curve_unaffected != expected.curve_unaffected
                    or any(abs(a - b) > 1e-5 for a, b in
                           zip(found.world_matrix, expected.world_matrix))):
                raise RuntimeError("控制器方向复检失败：坐标轴或世界矩阵不一致")


class DetachCustomControlOrientations:
    def __init__(self, host: ControlOrientationHost) -> None:
        self._host = host

    def apply(self, controls: tuple[str, ...]) -> tuple[str, ...]:
        states = self._host.capture_control_orientations(controls)
        if len(states) != len(controls) or not states:
            raise ValueError("手工方向需要当前角色的全部控制器")
        with self._host.transaction("分离全部控制器以手工调整方向"):
            proxies = self._host.detach_custom_control_orientations(states)
            captured = self._host.capture_custom_control_orientation_previews()
            if len(captured) != len(states) or any(
                    item.control != state.control
                    or any(abs(a - b) > 1e-5 for a, b in zip(
                        item.original_matrix, item.preview_matrix))
                    for item, state in zip(captured, states)):
                raise RuntimeError("控制器手工方向预览创建后复检失败")
        return proxies


class AttachCustomControlOrientations:
    def __init__(self, host: ControlOrientationHost) -> None:
        self._host = host

    def apply(self) -> int:
        previews = self._host.capture_custom_control_orientation_previews()
        states = self._host.capture_control_orientations(
            tuple(preview.control for preview in previews))
        changes = plan_custom_control_orientations(states, previews)
        unaffected = tuple(change.before.control for change in changes
                           if change.before.curve_unaffected)
        points = (self._host.capture_control_curve_world_points(unaffected)
                  if unaffected else ())
        with self._host.transaction("重新附着全部手工方向控制器"):
            for change in changes:
                self._host.apply_control_orientation(change.after)
            if points:
                self._host.restore_control_curve_world_points(points)
            self._host.finish_custom_control_orientations()
            found = self._host.capture_control_orientations(
                tuple(change.after.control for change in changes))
            if len(found) != len(changes) or any(
                    actual.control != change.after.control
                    or actual.primary_axis != change.after.primary_axis
                    or actual.secondary_axis != change.after.secondary_axis
                    or actual.curve_unaffected != change.after.curve_unaffected
                    or any(abs(a - b) > 1e-5 for a, b in zip(
                        actual.world_matrix, change.after.world_matrix))
                    for actual, change in zip(found, changes)):
                raise RuntimeError("控制器手工方向重新附着复检失败")
            if points:
                restored = self._host.capture_control_curve_world_points(unaffected)
                if (len(restored) != len(points) or any(
                        path != old_path or len(actual) != len(old)
                        or any(any(abs(a - b) > 1e-5 for a, b in zip(point, prior))
                               for point, prior in zip(actual, old))
                        for (path, actual), (old_path, old) in
                        zip(restored, points))):
                    raise RuntimeError("重新附着后曲线世界形状复检失败")
            self._host.read_character_registration()
        return len(changes)
