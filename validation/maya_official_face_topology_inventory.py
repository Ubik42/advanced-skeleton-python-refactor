"""Read-only inventory of boundary loops in a public Maya head/body asset."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om


def boundary_loops(mesh: str) -> list[dict]:
    selected = om.MSelectionList()
    selected.add(mesh)
    fn = om.MFnMesh(selected.getDagPath(0))
    edge_it = om.MItMeshEdge(selected.getDagPath(0))
    adjacency: dict[int, set[int]] = {}
    boundary_edges = 0
    while not edge_it.isDone():
        if edge_it.onBoundary():
            a, b = fn.getEdgeVertices(edge_it.index())
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
            boundary_edges += 1
        edge_it.next()
    loops = []
    seen = set()
    for start in adjacency:
        if start in seen:
            continue
        pending = [start]
        component = set()
        while pending:
            vertex = pending.pop()
            if vertex in component:
                continue
            component.add(vertex)
            pending.extend(adjacency[vertex] - component)
        seen.update(component)
        points = [fn.getPoint(index, om.MSpace.kWorld)
                  for index in component]
        mins = [min(point[axis] for point in points) for axis in range(3)]
        maxs = [max(point[axis] for point in points) for axis in range(3)]
        loops.append({
            "vertex_count": len(component),
            "closed": all(len(adjacency[index]) == 2 for index in component),
            "bounds_cm": [round(value, 5) for value in mins + maxs],
            "vertex_ids": sorted(component),
        })
    loops.sort(key=lambda row: (row["bounds_cm"][4], row["vertex_count"]),
               reverse=True)
    return loops


def main() -> None:
    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() == ".obj":
        cmds.file(new=True, force=True)
        cmds.loadPlugin("objExport", quiet=True)
        cmds.file(str(source), i=True, type="OBJ", options="mo=1",
                  ignoreVersion=True)
    elif source.suffix.lower() == ".fbx":
        cmds.file(new=True, force=True)
        cmds.loadPlugin("fbxmaya", quiet=True)
        cmds.file(str(source), i=True, type="FBX", ignoreVersion=True,
                  mergeNamespacesOnClash=False, options="fbx")
    else:
        cmds.file(str(source), open=True, force=True,
                  executeScriptNodes=False)
    meshes = cmds.ls(type="mesh", noIntermediate=True, long=True) or []
    rows = []
    for shape in meshes:
        parent = (cmds.listRelatives(shape, parent=True,
                                     fullPath=True) or [None])[0]
        loops = boundary_loops(shape)
        rows.append({
            "mesh": parent,
            "vertex_count": int(cmds.polyEvaluate(parent, vertex=True)),
            "face_count": int(cmds.polyEvaluate(parent, face=True)),
            "bounds_cm": [round(value, 5) for value in
                          cmds.exactWorldBoundingBox(parent)],
            "boundary_loop_count": len(loops),
            "boundary_loops": loops,
        })
    result = {"source_name": source.name,
              "has_face_fit": bool(cmds.ls("FaceFitSkeleton", type="transform")),
              "meshes": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Face topology inventory:", [(row["vertex_count"],
        row["boundary_loop_count"]) for row in rows], flush=True)


if __name__ == "__main__":
    main()
