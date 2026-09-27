"""Measure whether eyelid geometry actually hides the eyes at full blink."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om


def mesh_fn(name: str) -> om.MFnMesh:
    selection = om.MSelectionList()
    selection.add(name)
    return om.MFnMesh(selection.getDagPath(0))


def front_depth(mesh: om.MFnMesh, x: float, y: float) -> float | None:
    hit = mesh.closestIntersection(
        om.MFloatPoint(x, y, 1000.), om.MFloatVector(0., 0., -1.),
        om.MSpace.kWorld, 2000., False)
    return float(hit[0].z) if hit else None


def main() -> None:
    scene = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    head = mesh_fn("head")
    rows = {}
    for side, suffix in (("Right", "R"), ("Left", "L")):
        eye_name = cmds.skinCluster("AdvPy_EyeSkin_" + suffix,
                                    query=True, geometry=True)[0]
        eye = mesh_fn(eye_name)
        bounds = cmds.exactWorldBoundingBox(eye_name)
        cx = (bounds[0] + bounds[3]) / 2.
        cy = (bounds[1] + bounds[4]) / 2.
        rx = (bounds[3] - bounds[0]) / 2.
        ry = (bounds[4] - bounds[1]) / 2.
        points = [(cx + rx * ix / 10., cy + ry * iy / 10.)
                  for ix in range(-6, 7)
                  for iy in range(-3, 4)]
        visible = {}
        for label, blink in (("open", 0), ("closed", 10)):
            cmds.currentTime(1 if blink == 0 else 10, edit=True)
            cmds.setAttr("ctrlEye_R.blink", blink)
            cmds.setAttr("ctrlEye_L.blink", blink)
            visible_count = 0
            eye_hits = 0
            for x, y in points:
                eye_z = front_depth(eye, x, y)
                if eye_z is None:
                    continue
                eye_hits += 1
                lid_z = front_depth(head, x, y)
                if lid_z is None or eye_z > lid_z + .001:
                    visible_count += 1
            visible[label] = {"eye_hit_samples": eye_hits,
                              "visible_samples": visible_count,
                              "visible_fraction": round(
                                  visible_count / eye_hits, 6)
                              if eye_hits else None}
        rows[side] = visible
    passed = all(row["open"]["eye_hit_samples"] >= 50
                 and row["open"]["visible_fraction"] >= .3
                 and row["closed"]["visible_fraction"] <= .05
                 for row in rows.values())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"sides": rows, "passed": passed},
                                  ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Eye occlusion:", rows, "passed:", passed, flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
