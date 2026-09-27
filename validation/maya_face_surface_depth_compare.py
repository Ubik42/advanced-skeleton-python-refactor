"""Locate eye pixels that the original head covers but the rebuild exposes.

Inputs are two directories produced by the open/blink OBJ exporters. Maya
loads only their evaluated meshes; neither source scene is modified.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om


def imported(path: Path, name: str) -> tuple[str, om.MFnMesh]:
    nodes = cmds.file(str(path), i=True, type="OBJ", options="mo=1",
                      ignoreVersion=True, returnNewNodes=True)
    shapes = cmds.ls(nodes, long=True, type="mesh", noIntermediate=True) or []
    parents = {parent for shape in shapes for parent in
               (cmds.listRelatives(shape, parent=True, fullPath=True) or [])}
    if len(parents) != 1:
        raise ValueError(f"OBJ 必须恰有一个网格：{path}")
    node = cmds.rename(next(iter(parents)), name)
    selection = om.MSelectionList()
    selection.add(node)
    return node, om.MFnMesh(selection.getDagPath(0))


def front(mesh: om.MFnMesh, x: float, y: float) -> float | None:
    hit = mesh.closestIntersection(om.MFloatPoint(x, y, 1000.),
                                   om.MFloatVector(0., 0., -1.),
                                   om.MSpace.kWorld, 2000., False)
    return float(hit[0].z) if hit else None


def visible(eye: float | None, head: float | None,
            back: float) -> bool:
    return eye is not None and (head is None or head < back or eye > head + .001)


def main() -> None:
    original, product, output = (Path(value).resolve()
                                 for value in sys.argv[1:4])
    phase = sys.argv[4] if len(sys.argv) > 4 else "blink"
    if phase not in ("open", "blink"):
        raise ValueError("phase 必须为 open 或 blink")
    cmds.file(new=True, force=True)
    cmds.loadPlugin("objExport", quiet=True)
    meshes = {}
    for kind, folder in (("original", original), ("product", product)):
        for part in ("head", "right-eye", "left-eye"):
            meshes[kind, part] = imported(folder / f"{phase}-{part}.obj",
                                         kind + part.title().replace("-", ""))
    rows = {}
    for side, part in (("R", "right-eye"), ("L", "left-eye")):
        eye_name = meshes["product", part][0]
        bounds = cmds.exactWorldBoundingBox(eye_name)
        cx, cy = ((bounds[i] + bounds[i + 3]) / 2. for i in (0, 1))
        rx, ry = ((bounds[i + 3] - bounds[i]) / 2. for i in (0, 1))
        extra = []
        for ix in range(-30, 31):
            for iy in range(-30, 31):
                nx, ny = ix / 33., iy / 33.
                x, y = cx + rx * nx, cy + ry * ny
                new_eye = front(meshes["product", part][1], x, y)
                if new_eye is None:
                    continue
                old_eye = front(meshes["original", part][1], x, y)
                old_head = front(meshes["original", "head"][1], x, y)
                new_head = front(meshes["product", "head"][1], x, y)
                if (not visible(old_eye, old_head, bounds[2]) and
                        visible(new_eye, new_head, bounds[2])):
                    extra.append({"normalized_xy": [round(nx, 4), round(ny, 4)],
                                  "head_depth_difference_cm": (
                                      round(old_head - new_head, 6)
                                      if old_head is not None and
                                      new_head is not None else None),
                                  "product_eye_depth_deficit_cm": (
                                      round(new_eye - new_head, 6)
                                      if new_head is not None else None)})
        upper = [row for row in extra if row["normalized_xy"][1] > .1]
        depths = [row["product_eye_depth_deficit_cm"] for row in upper
                  if row["product_eye_depth_deficit_cm"] is not None]
        rows[side] = {"extra_visible_samples": len(extra),
                      "upper_extra_visible_samples": len(upper),
                      "upper_max_eye_depth_deficit_cm": max(depths, default=None),
                      "upper_mean_eye_depth_deficit_cm": (
                          round(sum(depths) / len(depths), 6) if depths else None),
                      "upper_examples": sorted(upper, key=lambda row:
                          row["product_eye_depth_deficit_cm"] or 0,
                          reverse=True)[:12]}
    report = {"phase": phase, "original": str(original),
              "product": str(product), "sides": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({side: {key: value for key, value in row.items()
                             if key != "upper_examples"}
                      for side, row in rows.items()}, ensure_ascii=False),
          flush=True)


if __name__ == "__main__":
    main()
