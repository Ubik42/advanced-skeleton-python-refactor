"""Delete complete Control Mesh groups without touching other scene meshes."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ControlMeshDeleteSource:
    control: str
    shapes: tuple[str, ...]
    helpers: tuple[str, ...]
    curve_visibility: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True, slots=True)
class ControlMeshDeleteItem:
    control: str
    shapes: tuple[str, ...]
    helpers: tuple[str, ...]
    curve_visibility: tuple[tuple[str, str | None], ...]


def plan_control_mesh_deletion(
    sources: tuple[ControlMeshDeleteSource, ...],
) -> tuple[ControlMeshDeleteItem, ...]:
    controls: set[str] = set()
    nodes: set[str] = set()
    items = []
    for source in sources:
        if (not source.control or source.control in controls
                or not source.shapes
                or len(set(source.shapes)) != len(source.shapes)
                or len(set(source.helpers)) != len(source.helpers)
                or any(not curve for curve, _ in source.curve_visibility)):
            raise ValueError("Control Mesh 删除来源无效")
        owned = set(source.shapes) | set(source.helpers)
        if len(owned) != len(source.shapes) + len(source.helpers) or nodes & owned:
            raise ValueError("Control Mesh 删除节点归属重复")
        nodes.update(owned)
        controls.add(source.control)
        items.append(ControlMeshDeleteItem(
            source.control, source.shapes, source.helpers,
            source.curve_visibility))
    if not items:
        raise ValueError("当前角色没有可删除的 Control Mesh")
    return tuple(items)
