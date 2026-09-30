"""Native selection implementation of ADV asSelectLeastEdgesPath (30617)."""

def original_face_least_edges(host,geometry,start,end):
    c=host._cmds; raw=getattr(c,"raw",c); mesh=host.scene_address(geometry)
    a,b=mesh+f".vtx[{start}]",mesh+f".vtx[{end}]"
    raw.select(a,replace=True); raw.polySelectConstraint(propagate=1,type=1)
    neighbors=raw.ls(selection=True,long=True,flatten=True) or []
    target=(raw.ls(b,long=True,flatten=True) or [b])[0]
    raw.select(mesh,replace=True)
    shortest=raw.polySelect(mesh,query=True,asSelectString=True,shortestEdgePath=(start,end)) or []
    if target in neighbors: return tuple(raw.ls(shortest,long=True,flatten=True) or [])
    raw.select((a,b),replace=True)
    candidate=raw.polySelectSp(query=True,loop=True) or []
    vertices=raw.ls(candidate,long=True,flatten=True) or []
    source=(raw.ls(a,long=True,flatten=True) or [a])[0]
    if source not in vertices or target not in vertices: vertices=[]
    if not vertices:
        candidate=raw.polySelectSp(query=True,ring=True) or []
        vertices=raw.ls(candidate,long=True,flatten=True) or []
        if target not in vertices: vertices=[]
    if len(vertices)>len(raw.ls(shortest,flatten=True) or [])+3: vertices=[]
    if vertices:
        edges=raw.polyListComponentConversion(vertices,toEdge=True,internal=True)
        return tuple(raw.ls(edges,long=True,flatten=True) or [])
    return tuple(raw.ls(shortest,long=True,flatten=True) or [])
