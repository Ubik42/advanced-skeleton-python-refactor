"""Create and verify Control Mesh shapes in one recoverable Maya action."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.control_mesh import (
    ControlMeshItem, ControlMeshSource, plan_control_mesh,
)


class ControlMeshHost(Protocol):
    def capture_control_mesh_source(
        self, global_control: str, mirror: bool,
    ) -> ControlMeshSource: ...
    def existing_control_mesh_names(self) -> frozenset[str]: ...
    def preflight_control_mesh(self, item: ControlMeshItem) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_control_mesh(self, item: ControlMeshItem) -> None: ...
    def capture_control_mesh(self, item: ControlMeshItem) -> bool: ...
    def capture_control_mesh_batch_sources(
        self, global_control: str, controls: tuple[str, ...],
    ) -> tuple[ControlMeshSource, ...]: ...


class CreateControlMesh:
    def __init__(self, host: ControlMeshHost) -> None:
        self._host = host

    def execute(self, global_control: str, *, mirror: bool = True
                ) -> tuple[ControlMeshItem, ...]:
        source = self._host.capture_control_mesh_source(
            global_control, mirror)
        plan = plan_control_mesh(
            source, self._host.existing_control_mesh_names())
        for item in plan:
            self._host.preflight_control_mesh(item)
        with self._host.transaction("创建 Control Mesh"):
            for item in plan:
                self._host.create_control_mesh(item)
            for item in plan:
                if not self._host.capture_control_mesh(item):
                    raise RuntimeError("Control Mesh 创建后结构不完整："
                                       + item.shape_name)
        return plan


class CreateControlMeshes:
    """Group each skinned mesh's faces by strongest joint and its FK control."""

    def __init__(self, host: ControlMeshHost) -> None:
        self._host = host

    def execute(self, global_control: str,
                controls: tuple[str, ...]) -> tuple[ControlMeshItem, ...]:
        sources = self._host.capture_control_mesh_batch_sources(
            global_control, controls)
        used = set(self._host.existing_control_mesh_names())
        plan = []
        for source in sources:
            items = plan_control_mesh(source, frozenset(used))
            plan.extend(items)
            used.update(name for item in items
                        for name in (item.shape_name,
                                     item.transform_name))
        if not plan:
            raise ValueError("所选 Skin 网格没有可对应到控制器的面")
        for item in plan:
            self._host.preflight_control_mesh(item)
        with self._host.transaction("批量创建 Control Mesh"):
            for item in plan:
                self._host.create_control_mesh(item)
            for item in plan:
                if not self._host.capture_control_mesh(item):
                    raise RuntimeError("Control Mesh 批量创建结果不完整："
                                       + item.shape_name)
        return tuple(plan)
