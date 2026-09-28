"""Assign original palette and expand each Control Mesh once."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.control_mesh_color import (
    ControlMeshColorItem, ControlMeshColorSource,
    plan_control_mesh_colors,
)


class ControlMeshColorHost(Protocol):
    def capture_control_mesh_color_sources(
        self, controls: tuple[str, ...],
    ) -> tuple[tuple[ControlMeshColorSource, ...], float]: ...
    def preflight_control_mesh_color(
        self, item: ControlMeshColorItem) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def ensure_control_mesh_shaders(self) -> None: ...
    def colorize_control_mesh(self, item: ControlMeshColorItem) -> None: ...
    def capture_control_mesh_color(
        self, item: ControlMeshColorItem) -> bool: ...


class ColorizeControlMeshes:
    def __init__(self, host: ControlMeshColorHost) -> None:
        self._host = host

    def execute(self, controls: tuple[str, ...]
                ) -> tuple[ControlMeshColorItem, ...]:
        sources, char_height = (
            self._host.capture_control_mesh_color_sources(controls))
        plan = plan_control_mesh_colors(sources, char_height)
        for item in plan:
            self._host.preflight_control_mesh_color(item)
        with self._host.transaction("Control Mesh 着色"):
            self._host.ensure_control_mesh_shaders()
            for item in plan:
                self._host.colorize_control_mesh(item)
            for item in plan:
                if not self._host.capture_control_mesh_color(item):
                    raise RuntimeError("Control Mesh 着色结果不完整："
                                       + item.mesh_shape)
        return plan
