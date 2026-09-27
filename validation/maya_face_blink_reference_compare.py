"""Compare original and reconstructed eyelid motion through a blink in Maya.

Both scenes are opened read-only. The two aim offsets are control values chosen
to produce the same measured eye rotation, not assumed equivalent distances.
"""
from __future__ import annotations

import json
from math import sqrt
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om


def mesh(name: str) -> om.MFnMesh:
    selection = om.MSelectionList()
    selection.add(name)
    return om.MFnMesh(selection.getDagPath(0))


def visible_samples(head: om.MFnMesh, eye: om.MFnMesh,
                    eye_name: str, center: bool) -> dict:
    bounds = cmds.exactWorldBoundingBox(eye_name)
    cx, cy = (bounds[0] + bounds[3]) / 2., (bounds[1] + bounds[4]) / 2.
    rx, ry = (bounds[3] - bounds[0]) / 2., (bounds[4] - bounds[1]) / 2.
    xs = range(-6, 7) if center else range(-9, 10)
    ys = range(-3, 4) if center else range(-9, 10)
    hits = visible = 0
    for ix in xs:
        for iy in ys:
            x, y = cx + rx * ix / 10., cy + ry * iy / 10.
            ray = om.MFloatPoint(x, y, 1000.)
            direction = om.MFloatVector(0., 0., -1.)
            eye_hit = eye.closestIntersection(ray, direction, om.MSpace.kWorld,
                                              2000., False)
            if not eye_hit:
                continue
            hits += 1
            head_hit = head.closestIntersection(ray, direction, om.MSpace.kWorld,
                                                2000., False)
            head_z = float(head_hit[0].z) if head_hit else None
            if head_z is None or head_z < bounds[2] or eye_hit[0].z > head_z + .001:
                visible += 1
    return {"eye_hits": hits, "visible": visible}


def sample(scene: Path, original: bool, aim_dx: float,
           fleshy_scale: float = 1.) -> dict:
    cmds.file(str(scene), open=True, force=True, executeScriptNodes=False)
    cmds.currentTime(1, edit=True)
    head = mesh("model:head" if original else "head")
    if not original and fleshy_scale != 1.:
        for control in cmds.ls("ctrl*EyeLid*", type="transform") or ():
            if cmds.attributeQuery("fleshy", node=control, exists=True):
                plug = control + ".fleshy"
                cmds.setAttr(plug, cmds.getAttr(plug) * fleshy_scale)
    eye_names = {side: ("model:eye" + side if original else
                 cmds.skinCluster("AdvPy_EyeSkin_" + side,
                                  query=True, geometry=True)[0])
                 for side in ("R", "L")}
    controls = {side: ("ctrlEye_" + side if original else
                       "AdvPy_EyeAim_" + side) for side in ("R", "L")}
    for control in controls.values():
        plug = control + ".translateX"
        cmds.setAttr(plug, cmds.getAttr(plug) + aim_dx)
    bounds = {side: cmds.exactWorldBoundingBox(name)
              for side, name in eye_names.items()}
    baseline = head.getPoints(om.MSpace.kWorld)
    indices = []
    for index, point in enumerate(baseline):
        if any((box[0] - .2 <= point.x <= box[3] + .2 and
                box[1] - .2 <= point.y <= box[4] + .2)
               for box in bounds.values()):
            indices.append(index)
    frames = {}
    visibility = {}
    eye_meshes = {side: mesh(name) for side, name in eye_names.items()}
    for blink in (0., 2.5, 5., 7.5, 10.):
        for side in ("R", "L"):
            cmds.setAttr("ctrlEye_" + side + ".blink", blink)
        points = head.getPoints(om.MSpace.kWorld)
        frames[str(blink)] = [[points[i].x, points[i].y, points[i].z]
                              for i in indices]
        visibility[str(blink)] = {
            side: {region: visible_samples(head, eye_meshes[side],
                                           eye_names[side], region == "center")
                   for region in ("center", "full_eye")}
            for side in ("R", "L")}
    rotation = {side: cmds.getAttr(("EyeJoint_" if original else
                                   "AdvPy_Eye_") + side + ".rotateY")
                for side in ("R", "L")}
    return {"vertex_count": head.numVertices, "indices": indices,
            "frames": frames, "eye_yaw_degrees": rotation,
            "visibility": visibility}


def rms(values: list[float]) -> float:
    return sqrt(sum(value * value for value in values) / len(values))


def main() -> None:
    source, product, output = (Path(value).resolve()
                               for value in sys.argv[1:4])
    original_dx = float(sys.argv[4])
    product_dx = float(sys.argv[5])
    fleshy_scale = float(sys.argv[6]) if len(sys.argv) > 6 else 1.
    reference = sample(source, True, original_dx)
    rebuilt = sample(product, False, product_dx, fleshy_scale)
    if reference["vertex_count"] != rebuilt["vertex_count"]:
        raise ValueError("原版与重构头部顶点数量不同")
    shared = sorted(set(reference["indices"]) & set(rebuilt["indices"]))
    if not shared:
        raise ValueError("未找到共同眼区顶点")
    rows = {}
    ref_index = {value: i for i, value in enumerate(reference["indices"])}
    new_index = {value: i for i, value in enumerate(rebuilt["indices"])}
    for blink in reference["frames"]:
        absolute = []
        motion = []
        for vertex in shared:
            i, j = ref_index[vertex], new_index[vertex]
            ref = reference["frames"][blink][i]
            new = rebuilt["frames"][blink][j]
            ref_open = reference["frames"]["0.0"][i]
            new_open = rebuilt["frames"]["0.0"][j]
            absolute.append(sqrt(sum((a - b) ** 2 for a, b in zip(ref, new))))
            motion.append(sqrt(sum(((a - ao) - (b - bo)) ** 2
                                   for a, ao, b, bo in
                                   zip(ref, ref_open, new, new_open))))
        rows[blink] = {"absolute_rms_cm": rms(absolute),
                       "absolute_max_cm": max(absolute),
                       "motion_rms_cm": rms(motion),
                       "motion_max_cm": max(motion),
                       "full_eye_visible_sample_error": {
                           side: rebuilt["visibility"][blink][side]["full_eye"]["visible"] -
                                 reference["visibility"][blink][side]["full_eye"]["visible"]
                           for side in ("R", "L")}}
    report = {"source": str(source), "product": str(product),
              "original_control_dx": original_dx,
              "product_aim_dx_cm": product_dx,
              "product_fleshy_scale": fleshy_scale,
              "original_yaw_degrees": reference["eye_yaw_degrees"],
              "product_yaw_degrees": rebuilt["eye_yaw_degrees"],
              "compared_head_vertices": len(shared),
              "blink": rows,
              "original_visibility": reference["visibility"],
              "product_visibility": rebuilt["visibility"],
              "matches_reference_within_10_samples": all(
                  abs(error) <= 10 for row in rows.values()
                  for error in row["full_eye_visible_sample_error"].values())}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
