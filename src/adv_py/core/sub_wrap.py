"""Selection plans for the original SubWrap operations."""
from __future__ import annotations

import re


_VERTEX = re.compile(r"^.+\.vtx\[[0-9]+(?::[0-9]+)?\]$")


def plan_wrap_targets(meshes: tuple[str, ...]) -> tuple[str, ...]:
    if not meshes or len(set(meshes)) != len(meshes) or any(
            not mesh or "." in mesh for mesh in meshes):
        raise ValueError("请选择唯一的待变形网格对象")
    return meshes


def plan_excluded_vertices(vertices: tuple[str, ...]) -> tuple[str, ...]:
    if not vertices or any(not _VERTEX.fullmatch(vertex)
                           for vertex in vertices):
        raise ValueError("请选择网格顶点")
    return tuple(dict.fromkeys(vertices))
