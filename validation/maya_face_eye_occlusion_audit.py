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
    original_meshes = sys.argv[3:6]
    if original_meshes and len(original_meshes) != 3:
        raise ValueError("原版对照需要头部、右眼和左眼三个网格名称")
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    head = mesh_fn(original_meshes[0] if original_meshes else "head")
    rows = {}
    full_rows = {}
    for side, suffix in (("Right", "R"), ("Left", "L")):
        eye_name = (original_meshes[1 if suffix == "R" else 2]
                    if original_meshes else cmds.skinCluster(
                        "AdvPy_EyeSkin_" + suffix,
                        query=True, geometry=True)[0])
        eye = mesh_fn(eye_name)
        bounds = cmds.exactWorldBoundingBox(eye_name)
        cx = (bounds[0] + bounds[3]) / 2.
        cy = (bounds[1] + bounds[4]) / 2.
        rx = (bounds[3] - bounds[0]) / 2.
        ry = (bounds[4] - bounds[1]) / 2.
        regions = {
            "center": [(cx + rx * ix / 10., cy + ry * iy / 10.)
                       for ix in range(-6, 7) for iy in range(-3, 4)],
            "full_eye": [(cx + rx * ix / 10., cy + ry * iy / 10.)
                         for ix in range(-9, 10) for iy in range(-9, 10)],
        }
        visible = {region: {} for region in regions}
        for label, blink in (("open", 0), ("closed", 10)):
            cmds.currentTime(1 if blink == 0 else 10, edit=True)
            cmds.setAttr("ctrlEye_R.blink", blink)
            cmds.setAttr("ctrlEye_L.blink", blink)
            for region, points in regions.items():
                visible_count = 0
                missing_front_surface = 0
                behind_eye = 0
                depth_deficits = []
                leaked_points = []
                eye_hits = 0
                for x, y in points:
                    eye_z = front_depth(eye, x, y)
                    if eye_z is None:
                        continue
                    eye_hits += 1
                    lid_z = front_depth(head, x, y)
                    if lid_z is None or eye_z > lid_z + .001:
                        visible_count += 1
                        if lid_z is None or lid_z < bounds[2]:
                            missing_front_surface += 1
                        else:
                            behind_eye += 1
                        if lid_z is not None:
                            depth_deficits.append(eye_z - lid_z)
                        if region == "full_eye" and label == "closed":
                            leaked_points.append({
                                "x_eye_radius": round((x - cx) / rx, 3),
                                "y_eye_radius": round((y - cy) / ry, 3),
                                "depth_deficit_cm": (round(eye_z - lid_z, 6)
                                                     if lid_z is not None else None)})
                visible[region][label] = {
                    "eye_hit_samples": eye_hits,
                    "visible_samples": visible_count,
                    "missing_front_surface_samples": missing_front_surface,
                    "surface_behind_eye_samples": behind_eye,
                    "largest_depth_deficit_cm": round(
                        max(depth_deficits, default=0.), 6),
                    "visible_fraction": round(
                        visible_count / eye_hits, 6) if eye_hits else None}
                if region == "full_eye" and label == "closed":
                    visible[region][label]["leaked_points"] = leaked_points
        rows[side] = visible["center"]
        full_rows[side] = visible["full_eye"]
    passed = all(row["open"]["eye_hit_samples"] >= 50
                 and row["open"]["visible_samples"] >= 20
                 and row["open"]["visible_fraction"] >=
                 row["closed"]["visible_fraction"] + .1
                 and row["closed"]["visible_fraction"] <= .01
                 for region in (rows, full_rows)
                 for row in region.values())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"sides": rows, "full_eye": full_rows,
                                  "passed": passed},
                                  ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    summary = {region: {side: {label: pose["visible_samples"]
                               for label, pose in side_rows.items()}
                        for side, side_rows in report.items()}
               for region, report in (("center", rows),
                                      ("full_eye", full_rows))}
    print("Eye occlusion samples:", summary,
          "passed:", passed, flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
