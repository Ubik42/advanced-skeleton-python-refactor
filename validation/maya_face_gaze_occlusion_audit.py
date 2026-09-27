"""Audit closed-eye occlusion while each Eye Aim changes direction."""
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


def measure(head: om.MFnMesh, eye: om.MFnMesh, eye_name: str,
            x_range: range, y_range: range) -> dict:
    bounds = cmds.exactWorldBoundingBox(eye_name)
    cx = (bounds[0] + bounds[3]) / 2.
    cy = (bounds[1] + bounds[4]) / 2.
    rx = (bounds[3] - bounds[0]) / 2.
    ry = (bounds[4] - bounds[1]) / 2.
    hits = visible = missing = 0
    deficit = 0.
    points = []
    for ix in x_range:
        for iy in y_range:
            x, y = cx + rx * ix / 10., cy + ry * iy / 10.
            eye_z = front_depth(eye, x, y)
            if eye_z is None:
                continue
            hits += 1
            lid_z = front_depth(head, x, y)
            if lid_z is None or lid_z < bounds[2] or eye_z > lid_z + .001:
                visible += 1
                absent_front = lid_z is None or lid_z < bounds[2]
                missing += absent_front
                if not absent_front:
                    deficit = max(deficit, eye_z - lid_z)
                points.append([ix / 10., iy / 10.])
    return {"eye_hits": hits, "visible": visible,
            "visible_fraction": round(visible / hits, 6) if hits else None,
            "missing_head_surface": missing,
            "max_depth_deficit_cm": round(deficit, 6),
            "leaked_points": points}


def main() -> None:
    scene, output = (Path(value).resolve() for value in sys.argv[1:3])
    delta = float(sys.argv[3]) if len(sys.argv) > 3 else .1
    fleshy_scale = float(sys.argv[4]) if len(sys.argv) > 4 else 1.
    vertical_scale = float(sys.argv[5]) if len(sys.argv) > 5 else 1.
    if delta <= 0:
        raise ValueError("Eye Aim 位移必须大于 0")
    cmds.file(str(scene), open=True, force=True, executeScriptNodes=False)
    if fleshy_scale != 1.:
        for control in cmds.ls("ctrl*EyeLid*", type="transform") or ():
            if cmds.attributeQuery("fleshy", node=control, exists=True):
                plug = control + ".fleshy"
                cmds.setAttr(plug, cmds.getAttr(plug) * fleshy_scale)
    if vertical_scale != 1.:
        for node in cmds.ls("ctrl*EyeLid*FleshyScale",
                            type="multiplyDivide") or ():
            plug = node + ".input2Y"
            cmds.setAttr(plug, cmds.getAttr(plug) * vertical_scale)
    head = mesh_fn("head")
    eyes = {side: (cmds.skinCluster("AdvPy_EyeSkin_" + suffix,
                                 query=True, geometry=True)[0])
            for side, suffix in (("Right", "R"), ("Left", "L"))}
    eye_fns = {side: mesh_fn(name) for side, name in eyes.items()}
    aim_plugs = {suffix + axis: "AdvPy_EyeAim_" + suffix + ".translate" + axis
                 for suffix in ("R", "L") for axis in "XY"}
    initial = {key: cmds.getAttr(plug) for key, plug in aim_plugs.items()}
    poses = {"neutral": (0., 0.), "right": (delta, 0.),
             "left": (-delta, 0.), "up": (0., delta),
             "down": (0., -delta)}
    rows = {}
    try:
        for label, (dx, dy) in poses.items():
            rows[label] = {}
            for blink_label, blink, frame in (("open", 0, 1),
                                               ("closed", 10, 10)):
                cmds.currentTime(frame, edit=True)
                for key, plug in aim_plugs.items():
                    cmds.setAttr(plug, initial[key] +
                                 (dx if key[-1] == "X" else dy))
                cmds.setAttr("ctrlEye_R.blink", blink)
                cmds.setAttr("ctrlEye_L.blink", blink)
                rows[label][blink_label] = {
                    side: {
                        "full_eye": measure(head, eye_fns[side], eye_name,
                                            range(-9, 10), range(-9, 10)),
                        "center": measure(head, eye_fns[side], eye_name,
                                          range(-6, 7), range(-3, 4))}
                    for side, eye_name in eyes.items()}
                rows[label][blink_label]["joint_rotation"] = {
                    suffix: cmds.getAttr("AdvPy_Eye_" + suffix + ".rotate")[0]
                    for suffix in ("R", "L")}
    finally:
        cmds.currentTime(1, edit=True)
        for key, plug in aim_plugs.items():
            cmds.setAttr(plug, initial[key])
    passed = all(
        rows[pose]["open"][side][region]["visible"] >= 20
        and rows[pose]["closed"][side][region]["visible_fraction"] <= .01
        for pose in poses for side in eyes for region in ("center", "full_eye"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"aim_delta_cm": delta,
                                  "fleshy_scale": fleshy_scale,
                                  "vertical_scale": vertical_scale,
                                  "initial_aim_translate": initial,
                                  "poses": rows,
                                  "passed": passed}, ensure_ascii=False,
                                 indent=2) + "\n", encoding="utf-8")
    print({pose: {side: {region: rows[pose]["closed"][side][region]["visible"]
                         for region in ("center", "full_eye")}
                  for side in eyes} for pose in poses}, "passed:", passed,
          flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
