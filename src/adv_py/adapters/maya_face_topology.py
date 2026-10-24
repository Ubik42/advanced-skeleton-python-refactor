"""Native selection implementation of ADV asSelectLeastEdgesPath (30617)."""

def original_face_least_edges(host,geometry,start,end):
    c=host._cmds
    raw=getattr(c,"raw",c)
    mesh=host.scene_address(geometry)
    a,b=mesh+f".vtx[{start}]",mesh+f".vtx[{end}]"

    def select(items):
        raw.select(items,replace=True) if items else raw.select(clear=True)

    def current():
        return tuple(raw.ls(selection=True,long=True,flatten=True) or [])

    def shortest():
        raw.select(mesh,replace=True)
        select(raw.polySelect(query=True,asSelectString=True,
                              shortestEdgePath=(start,end)) or [])
        return current()

    raw.select(a,replace=True)
    raw.polySelectConstraint(propagate=1,type=1)
    neighbors=current()
    raw.select(b,replace=True)
    target=current()[0]
    if target in neighbors:
        return shortest()

    raw.select(mesh,replace=True)
    raw.select((a,b),replace=True)
    source=(raw.ls(a,long=True,flatten=True) or [a])[0]
    candidate=raw.polySelectSp(query=True,loop=True) or []
    vertices=()
    if candidate:
        select(candidate)
        vertices=current()
        if source not in vertices or target not in vertices:
            raw.select(clear=True)
            vertices=()
    if not vertices:
        # Native queries ring against the selection left by the loop branch.
        # It does not silently restore the original endpoint pair here.
        candidate=raw.polySelectSp(query=True,ring=True) or []
        if candidate:
            select(candidate)
            vertices=current()
            if target not in vertices:
                raw.select(clear=True)
                vertices=()
    shortest_edges=shortest()
    if len(vertices)>len(shortest_edges)+3:
        vertices=()
    if vertices:
        select(vertices)
        select(raw.polyListComponentConversion(current(),toEdge=True,internal=True) or [])
        return current()
    # asSelectLeastEdgesPath leaves the chosen edges selected for its caller.
    return shortest()


def original_face_connected_vertices(host, geometry, seeds):
    """Convert vertices to their connected shells, as polyConvertToShell does.

    Read topology without changing Maya's persistent selection constraints.
    A shell conversion is not a constrained selection of the seed vertices:
    every vertex reachable by mesh edges must be included.
    """
    from maya.api import OpenMaya as om

    c = host._cmds
    raw = getattr(c, "raw", c)
    mesh = host.scene_address(geometry)
    shapes = raw.listRelatives(mesh, shapes=True, noIntermediate=True,
                               fullPath=True, type="mesh") or []
    if len(shapes) != 1:
        raise ValueError("Face shell conversion requires one visible mesh shape")
    selection = om.MSelectionList()
    selection.add(shapes[0])
    iterator = om.MItMeshVertex(selection.getDagPath(0))
    pending = [int(item.rsplit("[", 1)[1][:-1]) for item in seeds]
    visited = set(pending)
    while pending:
        iterator.setIndex(pending.pop())
        for index in iterator.getConnectedVertices():
            if index not in visited:
                visited.add(index)
                pending.append(index)
    path = (raw.ls(mesh, long=True) or [mesh])[0]
    return tuple(path + f".vtx[{index}]" for index in sorted(visited))
