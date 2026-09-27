"""Sample eye visibility in a read-only original AdvancedSkeleton Maya rig."""
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


def measure(head: om.MFnMesh, eye: om.MFnMesh,
            eye_name: str, center: bool) -> dict:
    bounds = cmds.exactWorldBoundingBox(eye_name)
    cx, cy = ((bounds[index] + bounds[index + 3]) / 2.
              for index in (0, 1))
    rx, ry = ((bounds[index + 3] - bounds[index]) / 2.
              for index in (0, 1))
    xs = range(-6, 7) if center else range(-9, 10)
    ys = range(-3, 4) if center else range(-9, 10)
    hits = visible = 0
    for ix in xs:
        for iy in ys:
            x, y = cx + rx * ix / 10., cy + ry * iy / 10.
            eye_z = front_depth(eye, x, y)
            if eye_z is None:
                continue
            hits += 1
            head_z = front_depth(head, x, y)
            if head_z is None or head_z < bounds[2] or eye_z > head_z + .001:
                visible += 1
    return {"eye_hits": hits, "visible": visible}


def main() -> None:
    scene = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    head_name, right_eye, left_eye = sys.argv[3:6]
    delta = float(sys.argv[6])
    if delta <= 0:
        raise ValueError("视线控制值变化必须大于零")
    cmds.file(str(scene), open=True, force=True, executeScriptNodes=False)
    cmds.currentTime(1, edit=True)
    head = mesh_fn(head_name)
    eyes = {"R": (right_eye, mesh_fn(right_eye)),
            "L": (left_eye, mesh_fn(left_eye))}
    initial = {side + axis: cmds.getAttr(
        "ctrlEye_" + side + ".translate" + axis)
        for side in ("R", "L") for axis in "XY"}
    poses = {"neutral": (0., 0.), "right": (delta, 0.),
             "left": (-delta, 0.), "up": (0., delta),
             "down": (0., -delta)}
    rows = {}
    for pose, (dx, dy) in poses.items():
        for key, value in initial.items():
            cmds.setAttr("ctrlEye_" + key[0] + ".translate" + key[1],
                         value + (dx if key[1] == "X" else dy))
        rows[pose] = {}
        for blink_name, blink in (("open", 0.), ("closed", 10.)):
            for side in ("R", "L"):
                cmds.setAttr("ctrlEye_" + side + ".blink", blink)
            rows[pose][blink_name] = {
                side: {region: measure(head, eye, name,
                                       region == "center")
                       for region in ("center", "full_eye")}
                for side, (name, eye) in eyes.items()}
        rows[pose]["joint_rotation"] = {
            side: cmds.getAttr("EyeJoint_" + side + ".rotate")[0]
            for side in ("R", "L")}
    report = {"source": str(scene), "control_delta": delta,
              "initial_control_translate": initial, "poses": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({pose: {side: {
        region: rows[pose]["open"][side][region]["visible"]
        for region in ("center", "full_eye")}
        for side in eyes} for pose in poses}), flush=True)


if __name__ == "__main__":
    main()
