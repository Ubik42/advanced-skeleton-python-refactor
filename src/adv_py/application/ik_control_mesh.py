"""Create IK curve meshes as one undoable character operation."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.ik_control_mesh import (
    IKControlCurve, IKControlMeshItem, plan_ik_control_meshes,
)


class IKControlMeshHost(Protocol):
    def capture_ik_control_curves(
        self, global_control: str,
    ) -> tuple[tuple[IKControlCurve, ...], float]: ...
    def existing_control_mesh_names(self) -> frozenset[str]: ...
    def preflight_ik_control_mesh(self, item: IKControlMeshItem) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def ensure_control_mesh_shaders(self) -> None: ...
    def create_ik_control_mesh(self, item: IKControlMeshItem) -> None: ...
    def capture_ik_control_mesh(self, item: IKControlMeshItem) -> bool: ...


class CreateIKControlMeshes:
    def __init__(self, host: IKControlMeshHost) -> None:
        self._host = host

    def execute(self, global_control: str) -> tuple[IKControlMeshItem, ...]:
        sources, scale = self._host.capture_ik_control_curves(global_control)
        plan = plan_ik_control_meshes(
            sources, scale, self._host.existing_control_mesh_names())
        if not plan:
            raise ValueError("ControlSet 中没有可生成网格的 IK 曲线")
        for item in plan:
            self._host.preflight_ik_control_mesh(item)
        with self._host.transaction("创建 IK Control Meshes"):
            self._host.ensure_control_mesh_shaders()
            for item in plan:
                self._host.create_ik_control_mesh(item)
            for item in plan:
                if not self._host.capture_ik_control_mesh(item):
                    raise RuntimeError("IK Control Mesh 创建结果不完整："
                                       + item.shape_name)
        return plan
