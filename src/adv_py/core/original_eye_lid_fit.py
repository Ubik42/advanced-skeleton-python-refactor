"""EyeLid branches of asCreateFaceFit, MEL 29647–30358.

Keep source extrema, component order, the two traversal caps, and max-Y
classification. The old average-height classifier is a different algorithm.
"""
from .face_eyelid_fit import EyeLidLoop


def order_original_eye_lid_loop(edges, positions, *, corner_vertices=(),
                                side='Right', cyclops=False, extra_main=False):
    if side not in ('Right', 'Left'):
        raise ValueError('眼睑侧别无效')
    edge_rows = tuple(sorted(edges))
    vertices = tuple(sorted({vertex for _, a, b in edge_rows for vertex in (a, b)}))
    if not vertices or any(vertex not in positions for vertex in vertices):
        raise ValueError('眼睑所选边没有可用顶点坐标')
    adjacency = {vertex: [] for vertex in vertices}
    for edge, a, b in edge_rows:
        adjacency[a].append((edge, b))
        adjacency[b].append((edge, a))
    if any(len(rows) != 2 for rows in adjacency.values()):
        raise ValueError('Not a complete edgeloop')
    tolerance = 9999 if side == 'Left' or cyclops and not extra_main else .001
    minimum_x = 999.
    maximum_x = maximum_y = -999.
    min_vertex = max_vertex = top_vertex = None
    for vertex in vertices:
        x, y, _ = positions[vertex]
        if x < minimum_x:
            minimum_x, min_vertex = x, vertex
        if x < tolerance:
            if x > maximum_x:
                maximum_x, max_vertex = x, vertex
            if y > maximum_y:
                maximum_y, top_vertex = y, vertex
    start, end = (min_vertex, max_vertex) if side == 'Left' else (max_vertex, min_vertex)
    if corner_vertices and not extra_main:
        # Native iteration retains the last two selected vertices. Its
        # numSelEdges array is not populated on the valid component branch,
        # so the subsequent 99-step grow does not replace this endpoint.
        start = corner_vertices[-1]
        if len(corner_vertices) > 1:
            end = corner_vertices[-2]
            swapped = positions[start][0] < positions[end][0]
            if side == 'Left':
                swapped = not swapped
            if swapped:
                start, end = end, start
    if start not in adjacency or end not in adjacency or start == end:
        raise ValueError('眼睑起点或终点不在所选边环上')
    first, second = adjacency[start]
    first_x = positions[start][0] + positions[first[1]][0]
    second_x = positions[start][0] + positions[second[1]][0]
    swap = first_x > second_x
    if side == 'Left':
        swap = not swap
    if swap:
        first, second = second, first

    def walk(first_edge, limit, *, require_progress):
        path = [start]
        current, blocked = start, first_edge[0]
        next_vertex = first_edge[1]
        for _ in range(limit):
            if next_vertex in path:
                if require_progress:
                    raise ValueError('Not a complete edgeloop')
                break
            path.append(next_vertex)
            if next_vertex == end:
                break
            current = next_vertex
            next_edge = next((row for row in adjacency[current] if row[0] != blocked), None)
            if next_edge is None:
                if require_progress:
                    raise ValueError('Not a complete edgeloop')
                break
            blocked, next_vertex = next_edge
        return tuple(path)

    one = walk(first, 199, require_progress=False)
    two = walk(second, 500, require_progress=True)
    upper, lower = (one, two) if top_vertex in one else (two, one)
    return EyeLidLoop(tuple(row[0] for row in edge_rows), upper, lower)
