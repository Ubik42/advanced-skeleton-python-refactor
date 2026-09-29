"""Create Shapers loops from a selected FK control."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.shapers_create import (ShapersFkLoop,
                                        ShapersFkLoopOptions,
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
