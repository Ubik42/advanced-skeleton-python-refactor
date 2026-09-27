"""Read the eyelid edge selections stored in an AdvancedSkeleton scene."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om

from adv_py.core.face_eyelid_fit import (
    eye_lid_blink_offsets, order_eye_lid_loop)


_EDGE = re.compile(r"^(?P<mesh>.+)\.e\[(?P<index>\d+)\]$")
_VERTEX = re.compile(r"^(?P<mesh>.+)\.vtx\[(?P<index>\d+)\]$")


def main() -> None:
    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    cmds.file(str(source), open=True, force=True,
              executeScriptNodes=False)
    rows = {}
    for layer in ("Inner", "Main", "Outer"):
        matches = cmds.ls("FaceFitEyeLid" + layer,
                          long=True, type="transform") or []
        if len(matches) != 1:
            raise RuntimeError("原版眼睑 Fit 节点缺失或重名：" + layer)
        tokens = (cmds.getAttr(matches[0] + ".selection") or "").split()
        edges = [_EDGE.fullmatch(token) for token in tokens]
        corners = [_VERTEX.fullmatch(token) for token in tokens]
        if not any(edges) or any(a is None and b is None
                               for a, b in zip(edges, corners)):
            raise RuntimeError("原版眼睑 Fit 边环记录无效：" + layer)
        mesh_names = {match.group("mesh") for match in edges + corners
                      if match is not None}
        if len(mesh_names) != 1:
            raise RuntimeError("眼睑 Fit 跨多个网格：" + layer)
        mesh_name = next(iter(mesh_names))
        selected = om.MSelectionList()
        selected.add(mesh_name)
        mesh = om.MFnMesh(selected.getDagPath(0))
        edge_ids = [int(match.group("index")) for match in edges
                    if match is not None]
        adjacency = {}
        for edge in edge_ids:
            first, second = mesh.getEdgeVertices(edge)
            adjacency.setdefault(first, set()).add(second)
            adjacency.setdefault(second, set()).add(first)
        vertices = set(adjacency)
        points = [mesh.getPoint(vertex, om.MSpace.kWorld)
                  for vertex in vertices]
        positions = {vertex: tuple(mesh.getPoint(
            vertex, om.MSpace.kWorld)[axis] for axis in range(3))
            for vertex in vertices}
        eye_fit = cmds.ls("FitEyeBall", type="transform") or []
        eye_y = (cmds.xform(eye_fit[0], query=True,
                            worldSpace=True, translation=True)[1]
                 if eye_fit else sum(point[1] for point in positions.values())
                 / len(positions))
        try:
            loop = order_eye_lid_loop(
                tuple((edge, *mesh.getEdgeVertices(edge))
                      for edge in edge_ids), positions,
                eye_center_y=eye_y, side="Right")
            eye_lid_blink_offsets(loop.upper_vertices,
                                  loop.lower_vertices, positions)
            blink_valid = True
        except ValueError:
            blink_valid = False
        boundary = set()
        edge_it = om.MItMeshEdge(selected.getDagPath(0))
        while not edge_it.isDone():
            if edge_it.onBoundary():
                boundary.add(edge_it.index())
            edge_it.next()
        rows[layer] = {
            "mesh": mesh_name,
            "edge_count": len(edge_ids),
            "vertex_count": len(vertices),
            "closed_selection": all(len(neighbors) == 2
                                    for neighbors in adjacency.values()),
            "endpoint_count": sum(len(neighbors) == 1
                                  for neighbors in adjacency.values()),
            "blink_curve_valid": blink_valid,
            "corner_count": sum(match is not None for match in corners),
            "boundary_edge_count": len(set(edge_ids) & boundary),
            "edge_points_cm": [
                [[round(float(mesh.getPoint(vertex, om.MSpace.kWorld)[axis]), 7)
                  for axis in range(3)]
                 for vertex in mesh.getEdgeVertices(edge)]
                for edge in edge_ids],
            "bounds_cm": [round(value, 6) for value in
                          [min(point[axis] for point in points)
                           for axis in range(3)]
                          + [max(point[axis] for point in points)
                             for axis in range(3)]],
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"source_name": source.name,
                                  "layers": rows}, ensure_ascii=False,
                                 indent=2) + "\n", encoding="utf-8")
    print("Original eyelid Fit:", rows, flush=True)


if __name__ == "__main__":
    main()
