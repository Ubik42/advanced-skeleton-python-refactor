"""Measure normal reversals and collapsed faces in a blinked eyelid band."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om


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
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    head = mesh_fn("head")
    rows = {}
    for side, suffix in (("Right", ""), ("Left", "Left")):
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
        cmds.setAttr("ctrlEye_R.blink", 0)
        cmds.setAttr("ctrlEye_L.blink", 0)
        opened = [(head.getPolygonNormal(index, om.MSpace.kWorld),
                   polygon_area(head, index))
                  for index in indices]
        cmds.currentTime(10, edit=True)
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
    passed = all(row["normal_reversed_faces"] == 0 and
                 row["collapsed_faces"] == 0 for row in rows.values())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"sides": rows, "passed": passed},
                                  ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Eyelid fold audit:", {side: {key: value for key, value in row.items()
          if not key.endswith("_ids")} for side, row in rows.items()},
          "passed:", passed, flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
