"""Measure the actual head-mesh eye-aperture gap after a full blink."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om

from adv_py.core.face_eyelid_fit import order_eye_lid_loop


def main() -> None:
    scene = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    cmds.file(str(scene), open=True, force=True, executeScriptNodes=False)
    selection = om.MSelectionList()
    selection.add("head")
    fn = om.MFnMesh(selection.getDagPath(0))
    rows = {}
    for side, suffix in (("Right", ""), ("Left", "Left")):
        holder = "FaceFitEyeLidInner" + suffix
        edge_ids = [int(item.split(".e[")[1][:-1]) for item in
                    (cmds.getAttr(holder + ".selection") or "").split()
                    if ".e[" in item]
        edges = tuple((index, *fn.getEdgeVertices(index))
                      for index in edge_ids)
        vertices = {vertex for _, first, second in edges
                    for vertex in (first, second)}
        cmds.currentTime(1, edit=True)
        neutral = {index: tuple(fn.getPoint(index, om.MSpace.kWorld)[axis]
                        for axis in range(3)) for index in vertices}
        loop = order_eye_lid_loop(edges, neutral,
            eye_center_y=sum(point[1] for point in neutral.values())
                         / len(neutral), side=side)
        x_min = max(min(neutral[index][0] for index in arc)
                    for arc in (loop.upper_vertices, loop.lower_vertices))
        x_max = min(max(neutral[index][0] for index in arc)
                    for arc in (loop.upper_vertices, loop.lower_vertices))
        xs = [x_min + (x_max-x_min) * fraction
              for fraction in (.2, .3, .4, .5, .6, .7, .8)]

        def gap(points, x):
            def height(arc):
                ordered = sorted((points[index][0], points[index][1])
                                 for index in arc)
                for first, second in zip(ordered, ordered[1:]):
                    if first[0] <= x <= second[0]:
                        t = (x-first[0])/(second[0]-first[0])
                        return first[1] + t*(second[1]-first[1])
                raise RuntimeError("孔沿弧未覆盖眼球中心")
            return height(loop.upper_vertices) - height(loop.lower_vertices)

        before = [gap(neutral, x) for x in xs]
        cmds.currentTime(10, edit=True)
        cmds.setAttr("ctrlEye_R.blink", 10)
        cmds.setAttr("ctrlEye_L.blink", 10)
        closed = {index: tuple(fn.getPoint(index, om.MSpace.kWorld)[axis]
                        for axis in range(3)) for index in vertices}
        after = [gap(closed, x) for x in xs]
        ratios = [value / original for value, original in zip(after, before)]
        rows[side] = {"center_open_gap_cm": round(before[3], 6),
                      "center_closed_gap_cm": round(after[3], 6),
                      "sample_ratios": [round(value, 6) for value in ratios],
                      "maximum_remaining_ratio": round(max(ratios), 6),
                      "minimum_remaining_ratio": round(min(ratios), 6)}
    passed = all(row["maximum_remaining_ratio"] <= .1
                 and row["minimum_remaining_ratio"] >= -.15
                 for row in rows.values())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"sides": rows, "passed": passed},
                                  ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Actual eye-aperture closure:", rows, "passed:", passed,
          flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
