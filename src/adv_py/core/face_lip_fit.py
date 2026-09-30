"""Lip branches of ADV 6.925 asCreateFaceFit, with topology traversal.

The selected edge ring is traversed in the original direction. Curve 2 omits
its initial point and discards the opposite half before the lower lip start.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True, slots=True)
class LipFitInput:
    mesh: str
    part: str
    edges: tuple[tuple[int,int,int], ...]
    corners: tuple[int, ...]
    positions: tuple[tuple[float,float,float], ...]
    mesh_edges: tuple[tuple[int,int], ...]
    face_vertices: tuple[tuple[int, ...], ...]
    non_symmetrical: bool = False
    previous_upper_start: int | None = None

@dataclass(frozen=True, slots=True)
class LipFitSide:
    suffix: str
    upper: tuple[int, ...]
    lower: tuple[int, ...]

@dataclass(frozen=True, slots=True)
class LipFitPlan:
    source: LipFitInput
    sides: tuple[LipFitSide, ...]


def _ring_graph(source):
    graph={}; seen=set()
    for edge,first,second in source.edges:
        if edge in seen or first==second or min(first,second)<0 or max(first,second)>=len(source.positions):
            raise ValueError("Lip 边索引或连接无效")
        seen.add(edge)
        for vertex,other in ((first,second),(second,first)):
            graph.setdefault(vertex,[]).append((edge,other))
    for neighbors in graph.values(): neighbors.sort()
    if len(graph)<4 or any(len(rows)!=2 for rows in graph.values()):
        raise ValueError("Lip 需要完整闭合边环，不能有分叉或断边")
    covered=set(); pending=[next(iter(graph))]
    while pending:
        vertex=pending.pop()
        if vertex in covered: continue
        covered.add(vertex); pending.extend(other for _,other in graph[vertex] if other not in covered)
    if covered!=set(graph): raise ValueError("Lip 选择包含多个不相连的边环")
    return graph


def _walk(graph,start,end,first_neighbor,limit):
    arc=[start]; previous=start; current=first_neighbor
    for _ in range(limit):
        if current==start: raise ValueError("Lip 遍历回到起点，指定嘴角不在路径上")
        arc.append(current)
        if current==end: return tuple(arc)
        remaining=[other for _,other in graph[current] if other!=previous]
        if len(remaining)!=1: raise ValueError("Lip 边环连接不唯一")
        previous,current=current,remaining[0]
    raise ValueError("Lip 遍历超过原版顶点步数上限")


def _adjacency(source):
    result=[set() for _ in source.positions]
    for first,second in source.mesh_edges:
        result[first].add(second); result[second].add(first)
    return result


def _upper_detector(source,first,second,max_y_vertex):
    one_is_upper=max_y_vertex in first
    if source.part=="Outer":
        return source.positions[first[0]][1]>source.positions[second[0]][1]
    if source.previous_upper_start is None: return one_is_upper
    adjacency=_adjacency(source)
    selected={source.previous_upper_start}
    # Main uses Outer and grows 18 times; Inner uses Main and grows 10 times.
    for _ in range(18 if source.part=="Main" else 10):
        selected|={other for vertex in selected for other in adjacency[vertex]}
        if first[0] in selected: return True
        if second[0] in selected: return False
    return one_is_upper


def _arcs(source,graph,start,end,lip_starts,left=False,forced_lower=None):
    neighbors=[other for _,other in graph[start]]
    # xform(edge) returns two endpoints; comparing their X sums is equivalent
    # to comparing the neighbor X at the common start, preserving Maya ties.
    first,second=neighbors
    condition=source.positions[first][0]>source.positions[second][0]
    if left: condition=not condition
    if condition: first,second=second,first
    first_arc=_walk(graph,start,end,first,199)
    second_full=_walk(graph,start,end,second,500)
    hit=False; second_arc=[]
    threshold=source.positions[forced_lower][0]-.001 if forced_lower is not None else .001
    for index,vertex in enumerate(second_full[1:]):
        if index>0 and lip_starts and vertex in lip_starts: hit=True
        if lip_starts and not hit: continue
        if not lip_starts:
            if forced_lower is None and source.positions[vertex][0]>threshold: continue
            if forced_lower is not None and source.positions[vertex][0]<threshold: continue
        second_arc.append(vertex)
    if min(len(first_arc),len(second_arc))<2:
        raise ValueError("Lip 上下半边不足两个顶点，请按原版选择两个中心点和一个嘴角")
    return first_arc,tuple(second_arc),second_full


def plan_lip_fit(source: LipFitInput) -> LipFitPlan:
    if source.part not in ("Outer","Main","Inner"): raise ValueError("Lip Fit 层级无效")
    if len(source.corners) not in (0,3) or len(set(source.corners))!=len(source.corners):
        raise ValueError("Lip 顶点指定必须是零个或三个不同顶点")
    if any(len(point)!=3 or not all(isfinite(value) for value in point) for point in source.positions):
        raise ValueError("Lip 顶点坐标无效")
    graph=_ring_graph(source)
    if any(vertex not in graph for vertex in source.corners):
        raise ValueError("Lip 指定顶点必须在所选边环上")
    vertices=sorted(graph)
    extrema=vertices
    if source.part=="Outer":
        average=sum(source.positions[v][1] for v in vertices)/len(vertices)
        extrema=[v for v in vertices if source.positions[v][1]>average]
    central=[v for v in extrema if source.positions[v][0]<.001]
    if not central: raise ValueError("Lip 边环缺少原版右半边或中心点")
    start=max(central,key=lambda v:source.positions[v][0])
    end=min(extrema,key=lambda v:source.positions[v][0])
    if source.corners:
        candidates=[v for v in source.corners if v!=start]
        if candidates: end=min(candidates,key=lambda v:source.positions[v][0])
    lip_starts=tuple(v for v in source.corners if v!=end)
    if len(lip_starts)==1: lip_starts=()
    if len(lip_starts)>1: start=max(lip_starts,key=lambda v:source.positions[v][1])
    if start==end: raise ValueError("Lip 中心点和嘴角重合")
    first,second,opposite=_arcs(source,graph,start,end,lip_starts)
    max_y=max(central,key=lambda v:source.positions[v][1])
    one_upper=_upper_detector(source,first,second,max_y)
    upper,lower=(first,second) if one_upper else (second,first)
    right=LipFitSide("",upper,lower)
    sides=[right]
    if source.non_symmetrical:
        # Original grows from upper CV0 along the whole loop for spans-1,
        # then chooses the new boundary vertex outside the right-half arcs.
        allowed=set(graph); adjacency=_adjacency(source); grown={upper[0]}
        for _ in range(len(upper)-2):
            grown|={n for v in grown for n in adjacency[v] if n in allowed}
        expanded=grown|{n for v in grown for n in adjacency[v]}
        candidates=sorted((expanded-grown)&allowed-set(upper)-set(lower))
        if not candidates: raise ValueError("原版 Lip 非对称遍历找不到左侧嘴角")
        left_end=candidates[-1] # MEL overwrites end with the last ls vertex.
        first_l,second_l,_=_arcs(source,graph,upper[0],left_end,(upper[0],lower[0]),
                                left=True,forced_lower=lower[0])
        max_y_l=max(vertices,key=lambda v:source.positions[v][1])
        upper_l,lower_l=(first_l,second_l) if _upper_detector(source,first_l,second_l,max_y_l) else (second_l,first_l)
        if len(upper_l)!=len(upper) or len(lower_l)!=len(lower):
            raise ValueError("原版要求左右 Lip 曲线 CV 数一致："
                f"upper {len(upper)}/{len(upper_l)}, lower {len(lower)}/{len(lower_l)}")
        sides.append(LipFitSide("Left",upper_l,lower_l))
    return LipFitPlan(source,tuple(sides))


def lip_inner_area(source: LipFitInput, outer_vertices: tuple[int,...],
                   seed: int) -> tuple[int,...]:
    """Original 199-step vertex growth excluding Outer and Inner borders."""
    adjacency=_adjacency(source)
    border=set(outer_vertices)|{v for _,a,b in source.edges for v in (a,b)}
    if seed<0 or seed>=len(adjacency): raise ValueError("Lip Main 中点采样顶点无效")
    selected={seed}
    previous_count=0
    for _ in range(199):
        selected=(selected|{n for v in selected for n in adjacency[v]})-border
        if len(selected)==previous_count: break
        previous_count=len(selected)
    # ConvertSelectionToFaces includes faces incident to selected vertices.
    return tuple(index for index,vertices in enumerate(source.face_vertices)
                 if set(vertices)&selected)
