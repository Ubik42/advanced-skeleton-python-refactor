"""Measure normal reversals and collapsed faces in a blinked eyelid band."""
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
from adv_py.core.face_eyelid_fit import eye_lid_area_faces


def mesh_fn(name: str) -> om.MFnMesh:
    selection = om.MSelectionList()
    selection.add(name)
    return om.MFnMesh(selection.getDagPath(0))


def polygon_area(mesh: om.MFnMesh, index: int) -> float:
    vertices = mesh.getPolygonVertices(index)
    points = [mesh.getPoint(vertex, om.MSpace.kWorld)
              for vertex in vertices]
    return sum(((points[index] - points[0]) ^
                (points[index + 1] - points[0])).length() / 2.
               for index in range(1, len(points) - 1))


def main() -> None:
    scene = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    original_head = (sys.argv[3] if len(sys.argv) > 3
                     and sys.argv[3] != "-" else None)
    aim_dx = float(sys.argv[4]) if len(sys.argv) > 4 else 0.
    aim_dy = float(sys.argv[5]) if len(sys.argv) > 5 else 0.
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    aim_initial = {}
    if not original_head:
        cmds.currentTime(1, edit=True)
        aim_initial = {suffix + axis: cmds.getAttr(
            "AdvPy_EyeAim_" + suffix + ".translate" + axis)
            for suffix in ("R", "L") for axis in "XY"}
    def set_aim():
        for key, value in aim_initial.items():
            cmds.setAttr("AdvPy_EyeAim_" + key[0] + ".translate" + key[1],
                         value + (aim_dx if key[1] == "X" else aim_dy))
    head = mesh_fn(original_head or "head")
    rows = {}
    for side, suffix in (("Right", ""), ("Left", "Left")):
        if original_head and side == "Left":
            continue
        if original_head:
            rings = {}
            for layer in ("Outer", "Main", "Inner"):
                holder = (cmds.ls("FaceFitEyeLid" + layer,
                                  long=True, type="transform") or [None])[0]
                if holder is None:
                    raise RuntimeError("原版眼睑 Fit 缺失：" + layer)
                selected = cmds.getAttr(holder + ".selection") or ""
                rings[layer] = tuple(int(match.group(1))
                    for component in selected.split()
                    if (match := re.search(r"\.e\[(\d+)\]$", component)))
            selection = om.MSelectionList()
            selection.add(original_head)
            dag = selection.getDagPath(0)
            polygon_it = om.MItMeshPolygon(dag)
            face_edges = []
            while not polygon_it.isDone():
                face_edges.append(tuple(polygon_it.getEdges()))
                polygon_it.next()
            edge_it = om.MItMeshEdge(dag)
            edge_faces = []
            while not edge_it.isDone():
                edge_faces.append(tuple(edge_it.getConnectedFaces()))
                edge_it.next()
            indices = list(eye_lid_area_faces(
                tuple(face_edges), tuple(edge_faces),
                outer_edges=rings["Outer"], main_edges=rings["Main"],
                inner_edges=rings["Inner"]))
        else:
            area = (cmds.ls("EyeLidInnerAreaMesh" + suffix,
                            long=True, type="transform") or [None])[0]
            if area is None:
                raise RuntimeError(side + " 眼睑区域网格缺失")
            selected = cmds.getAttr(area + ".selection") or ""
            indices = [int(match.group(1)) for component in selected.split()
                       if (match := re.search(r"\.f\[(\d+)\]$", component))]
        if not indices or len(indices) != len(set(indices)):
            raise RuntimeError(side + " 眼睑区域面记录无效")
        cmds.currentTime(1, edit=True)
        set_aim()
        cmds.setAttr("ctrlEye_R.blink", 0)
        cmds.setAttr("ctrlEye_L.blink", 0)
        opened = [(head.getPolygonNormal(index, om.MSpace.kWorld),
                   polygon_area(head, index))
                  for index in indices]
        cmds.currentTime(10, edit=True)
        set_aim()
        cmds.setAttr("ctrlEye_R.blink", 10)
        cmds.setAttr("ctrlEye_L.blink", 10)
        closed = [(head.getPolygonNormal(index, om.MSpace.kWorld),
                   polygon_area(head, index))
                  for index in indices]
        flipped = []
        collapsed = []
        for index, (before, after) in zip(indices, zip(opened, closed)):
            normal_open, area_open = before
            normal_closed, area_closed = after
            if normal_open * normal_closed < 0:
                flipped.append(index)
            if area_open > 1e-10 and area_closed / area_open < .05:
                collapsed.append(index)
        rows[side] = {"area_faces": len(indices),
                      "normal_reversed_faces": len(flipped),
                      "collapsed_faces": len(collapsed),
                      "normal_reversed_face_ids": flipped,
                      "collapsed_face_ids": collapsed}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"sides": rows,
                                  "diagnostic_only": True},
                                  ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Eyelid fold audit:", {side: {key: value for key, value in row.items()
          if not key.endswith("_ids")} for side, row in rows.items()},
          flush=True)


if __name__ == "__main__":
    main()
