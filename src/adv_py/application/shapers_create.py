"""Create Shapers loops from a selected FK control."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.shapers_create import (ShapersFkLoop,
                                        ShapersFkLoopOptions,
                                        ShapersEdge,
                                        ShapersEdgePack,
                                        plan_shapers_edge_packs,
                                        plan_shapers_fk_loops)


class ShapersCreateHost(Protocol):
    def selected_fk_controls(self) -> tuple[str, ...]: ...
    def preflight_fk_loops(self, loops: tuple[ShapersFkLoop, ...],
                           mesh: str) -> None: ...
    def create_fk_loops(self, loops: tuple[ShapersFkLoop, ...],
                        mesh: str, options: ShapersFkLoopOptions) -> int: ...


class CreateShapersFkLoops:
    def __init__(self, host: ShapersCreateHost) -> None:
        self.host = host

    def execute(self, mesh: str, options: ShapersFkLoopOptions) -> int:
        if not mesh:
            raise ValueError("请先在 Preparation / Rig 指定 Skin 网格")
        loops = plan_shapers_fk_loops(self.host.selected_fk_controls(),
                                      options)
        self.host.preflight_fk_loops(loops, mesh)
        return self.host.create_fk_loops(loops, mesh, options)


class ShapersEdgeHost(Protocol):
    def capture_edge_input(self) -> tuple[
        str, tuple[ShapersEdge, ...],
        dict[int, tuple[float, float, float]], int | None]: ...
    def preflight_edge_packs(self, mesh: str,
                             packs: tuple[ShapersEdgePack, ...]) -> None: ...
    def create_edge_packs(self, mesh: str,
                          packs: tuple[ShapersEdgePack, ...],
                          options: ShapersFkLoopOptions) -> int: ...


class CreateShapersEdgePacks:
    def __init__(self, host: ShapersEdgeHost) -> None:
        self.host = host

    def execute(self, options: ShapersFkLoopOptions) -> int:
        mesh, edges, positions, start_vertex = self.host.capture_edge_input()
        packs = plan_shapers_edge_packs(edges, positions, start_vertex)
        self.host.preflight_edge_packs(mesh, packs)
        return self.host.create_edge_packs(mesh, packs, options)
