"""Remove selected or all Control Mesh shapes as one Maya undo action."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.control_mesh_delete import (
    ControlMeshDeleteItem, ControlMeshDeleteSource,
    plan_control_mesh_deletion,
)


class ControlMeshDeleteHost(Protocol):
    def capture_control_mesh_delete_sources(
        self, global_control: str, selected_only: bool,
    ) -> tuple[ControlMeshDeleteSource, ...]: ...
    def preflight_control_mesh_deletion(
        self, item: ControlMeshDeleteItem,
    ) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def delete_control_meshes(self, item: ControlMeshDeleteItem) -> None: ...
    def capture_control_mesh_deletion(
        self, item: ControlMeshDeleteItem,
    ) -> bool: ...


class DeleteControlMeshes:
    def __init__(self, host: ControlMeshDeleteHost) -> None:
        self._host = host

    def execute(self, global_control: str, *, selected_only: bool
                ) -> tuple[ControlMeshDeleteItem, ...]:
        sources = self._host.capture_control_mesh_delete_sources(
            global_control, selected_only)
        plan = plan_control_mesh_deletion(sources)
        for item in plan:
            self._host.preflight_control_mesh_deletion(item)
        with self._host.transaction("删除 Control Meshes"):
            for item in plan:
                self._host.delete_control_meshes(item)
            for item in plan:
                if not self._host.capture_control_mesh_deletion(item):
                    raise RuntimeError("Control Mesh 删除结果不完整："
                                       + item.control)
        return plan
