"""SubWrap user operations, with scene readback after each mutation."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.sub_wrap import plan_excluded_vertices, plan_wrap_targets


class SubWrapHost(Protocol):
    def transaction(self, label: str): ...
    def preflight_cage(self, *, creating: bool) -> None: ...
    def create_cage(self) -> None: ...
    def delete_cage(self) -> None: ...
    def cage_present(self) -> bool: ...
    def selected_meshes(self) -> tuple[str, ...]: ...
    def preflight_wrap(self, meshes: tuple[str, ...]) -> None: ...
    def wrap_mesh(self, mesh: str) -> None: ...
    def mesh_wrapped(self, mesh: str) -> bool: ...
    def detached_meshes(self) -> tuple[str, ...]: ...
    def detach_all(self) -> tuple[str, ...]: ...
    def selected_vertices(self) -> tuple[str, ...]: ...
    def exclude_vertices(self, vertices: tuple[str, ...]) -> None: ...
    def vertices_excluded(self, vertices: tuple[str, ...]) -> bool: ...


class SubWrapOperations:
    def __init__(self, host: SubWrapHost) -> None:
        self.host = host

    def create_cage(self) -> None:
        self.host.preflight_cage(creating=True)
        with self.host.transaction("创建 SubWrap 笼体"):
            self.host.create_cage()
            if not self.host.cage_present():
                raise RuntimeError("SubWrap 笼体创建后缺少网格或显示层")

    def delete_cage(self) -> None:
        self.host.preflight_cage(creating=False)
        with self.host.transaction("删除 SubWrap 笼体"):
            self.host.delete_cage()
            if self.host.cage_present():
                raise RuntimeError("SubWrap 笼体删除后仍存在")

    def wrap_selected(self) -> int:
        meshes = plan_wrap_targets(self.host.selected_meshes())
        self.host.preflight_wrap(meshes)
        with self.host.transaction("SubWrap 包裹所选网格"):
            for mesh in meshes:
                self.host.wrap_mesh(mesh)
            if any(not self.host.mesh_wrapped(mesh) for mesh in meshes):
                raise RuntimeError("SubWrap 变形器创建后未连接全部网格")
        return len(meshes)

    def detach(self) -> int:
        with self.host.transaction("解除 SubWrap 包裹"):
            meshes = self.host.detach_all()
            if any(self.host.mesh_wrapped(mesh) for mesh in meshes):
                raise RuntimeError("SubWrap 解除后仍连接网格")
        return len(meshes)

    def attach(self) -> int:
        meshes = plan_wrap_targets(self.host.detached_meshes())
        self.host.preflight_wrap(meshes)
        with self.host.transaction("恢复 SubWrap 包裹"):
            for mesh in meshes:
                self.host.wrap_mesh(mesh)
            if any(not self.host.mesh_wrapped(mesh) for mesh in meshes):
                raise RuntimeError("SubWrap 恢复后未连接全部网格")
        return len(meshes)

    def exclude_selected(self) -> int:
        vertices = plan_excluded_vertices(self.host.selected_vertices())
        with self.host.transaction("排除 SubWrap 顶点"):
            self.host.exclude_vertices(vertices)
            if not self.host.vertices_excluded(vertices):
                raise RuntimeError("SubWrap 顶点排除后集合状态不一致")
        return len(vertices)
