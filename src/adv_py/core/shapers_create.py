"""Plan the FK-controller loop branch of AdvancedSkeleton Shapers creation."""
from __future__ import annotations

from dataclasses import dataclass
import re


_PYTHON_FK = re.compile(r"AdvPy_(.+)FK_([MRL])$")
_ORIGINAL_FK = re.compile(r"FK(.+)_([MRL])$")


@dataclass(frozen=True, slots=True)
class ShapersFkLoopOptions:
    loop_controls: int = 4
    snap_vertices: bool = True
    mirror: bool = True
    bridge_controls: int = 3
    bridge_snap_vertices: bool = False

    def __post_init__(self) -> None:
        if (type(self.loop_controls) is not int or self.loop_controls < 3
                or type(self.snap_vertices) is not bool
                or type(self.mirror) is not bool
                or type(self.bridge_controls) is not int
                or self.bridge_controls < 3
                or type(self.bridge_snap_vertices) is not bool):
            raise ValueError("Shapers 闭环参数无效")


@dataclass(frozen=True, slots=True)
class ShapersFkLoop:
    control: str
    deform_joint: str
    fit_stem: str
    side: str


@dataclass(frozen=True, slots=True)
class ShapersEdge:
    index: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ShapersEdgePack:
    edges: tuple[int, ...]
    vertices: tuple[int, ...]
    closed: bool


def plan_shapers_edge_packs(
    edges: tuple[ShapersEdge, ...],
    positions: dict[int, tuple[float, float, float]],
    start_vertex: int | None = None,
) -> tuple[ShapersEdgePack, ...]:
    """Partition selected edges into ordered, non-branching paths or rings."""
    if not edges or len({edge.index for edge in edges}) != len(edges):
        raise ValueError("请选择不重复的网格边")
    adjacent: dict[int, list[tuple[int, int]]] = {}
    for edge in edges:
        if (edge.start == edge.end or edge.start not in positions
                or edge.end not in positions):
            raise ValueError("Shapers 边拓扑或顶点位置无效")
        adjacent.setdefault(edge.start, []).append((edge.end, edge.index))
        adjacent.setdefault(edge.end, []).append((edge.start, edge.index))
    if any(len(neighbors) > 2 for neighbors in adjacent.values()):
        raise ValueError("Shapers 选边不能有分叉顶点")
    remaining = {edge.index for edge in edges}
    packs = []
    while remaining:
        seed = next(edge for edge in edges if edge.index in remaining)
        component = {seed.start, seed.end}
        frontier = [seed.start, seed.end]
        while frontier:
            vertex = frontier.pop()
            for neighbor, _ in adjacent[vertex]:
                if neighbor not in component:
                    component.add(neighbor)
                    frontier.append(neighbor)
        endpoints = [vertex for vertex in component
                     if len(adjacent[vertex]) == 1]
        if len(endpoints) not in (0, 2):
            raise ValueError("Shapers 选边必须构成闭环或开放单链")
        closed = not endpoints
        if closed:
            if start_vertex in component:
                first = start_vertex
            else:
                coordinates = [positions[vertex] for vertex in component]
                spans = [max(point[axis] for point in coordinates) -
                         min(point[axis] for point in coordinates)
                         for axis in range(3)]
                twist_axis = min(range(3), key=lambda axis: spans[axis])
                start_axis = 2 if twist_axis == 1 else 1
                first = max(component, key=lambda vertex:
                            (positions[vertex][start_axis], -vertex))
        else:
            first = (start_vertex if start_vertex in endpoints else
                     min(endpoints))
        vertices = [first]
        edge_indices = []
        current = first
        previous = None
        while True:
            choices = [(neighbor, edge_index)
                       for neighbor, edge_index in adjacent[current]
                       if edge_index in remaining]
            if not choices:
                break
            if previous is None and len(choices) == 2 and closed:
                a, b = choices
                axis = min(range(3), key=lambda coordinate:
                           max(positions[v][coordinate] for v in component) -
                           min(positions[v][coordinate] for v in component))
                direction = 2 if axis == 0 else 0
                reverse = axis == 1
                choices.sort(key=lambda item: positions[item[0]][direction],
                             reverse=reverse)
            neighbor, edge_index = choices[0]
            remaining.remove(edge_index)
            edge_indices.append(edge_index)
            previous, current = current, neighbor
            if current == first:
                break
            vertices.append(current)
        if len(edge_indices) != len(component) - (0 if closed else 1):
            raise ValueError("Shapers 选边存在未覆盖的分叉或重复路径")
        packs.append(ShapersEdgePack(tuple(edge_indices),
                                     tuple(vertices), closed))
    if len(packs) > 1:
        centers = [tuple(sum(positions[vertex][axis]
                             for vertex in pack.vertices) / len(pack.vertices)
                         for axis in range(3)) for pack in packs]
        spread = [max(center[axis] for center in centers) -
                  min(center[axis] for center in centers)
                  for axis in range(3)]
        axis = max(range(3), key=lambda index: spread[index])
        packs.sort(key=lambda pack: sum(positions[vertex][axis]
                                        for vertex in pack.vertices) /
                   len(pack.vertices))
    return tuple(packs)


def plan_shapers_fk_loops(
    controls: tuple[str, ...], options: ShapersFkLoopOptions,
) -> tuple[ShapersFkLoop, ...]:
    if len(controls) != 1:
        raise ValueError("当前 FK 闭环路径一次选择一个 FK 控制器")
    control = controls[0]
    leaf = control.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    match = _PYTHON_FK.fullmatch(leaf) or _ORIGINAL_FK.fullmatch(leaf)
    if match is None:
        raise ValueError("请选择 Body FK 控制器")
    stem, side = match.groups()
    if not stem or stem.endswith("Offset") or stem.endswith("Extra"):
        raise ValueError("请选择 FK 控制曲线，而非接收层")
    prefix = control.rsplit("|", 1)[-1].removesuffix(leaf)
    loops = [ShapersFkLoop(control, prefix + stem + "_" + side, stem,
                           "_" + side)]
    if options.mirror and side in ("R", "L"):
        opposite = "L" if side == "R" else "R"
        mirror_leaf = leaf[:-1] + opposite
        loops.append(ShapersFkLoop(prefix + mirror_leaf,
                                   prefix + stem + "_" + opposite,
                                   stem, "_" + opposite))
    return tuple(loops)
