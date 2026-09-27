"""Count outward eyelid faces whose shaded corner normals point backward.

The source Maya scene is opened read only. The report separates neutral,
downward gaze, and full blink; it does not infer geometric quality from normal
counts alone.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om


def main() -> None:
    scene = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    down_cm = float(sys.argv[3]) if len(sys.argv) > 3 else 3.
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    selected = om.MSelectionList()
    selected.add(cmds.listRelatives("head", shapes=True,
                                   noIntermediate=True,
                                   fullPath=True)[0])
    mesh = om.MFnMesh(selected.getDagPath(0))
    areas = {}
    for side, suffix in (("Right", ""), ("Left", "Left")):
        holder = cmds.ls("EyeLidInnerAreaMesh" + suffix,
                         long=True, type="transform")
        if len(holder) != 1:
            raise RuntimeError(side + " 眼睑区域缺失或重名")
        selection = cmds.getAttr(holder[0] + ".selection") or ""
        faces = [int(index) for index in re.findall(r"\.f\[(\d+)\]",
                                                  selection)]
        if not faces or len(faces) != len(set(faces)):
            raise RuntimeError(side + " 眼睑区域面无效")
        areas[side] = faces
    start_aim = {suffix: cmds.getAttr(
        "AdvPy_EyeAim_" + suffix + ".translateY")
        for suffix in ("R", "L")}
    poses = {}
    for label, offset, blink in (("neutral", 0., 0.),
                                  ("down_open", -down_cm, 0.),
                                  ("down_blink", -down_cm, 10.)):
        cmds.currentTime(1, edit=True)
        for suffix in ("R", "L"):
            cmds.setAttr("AdvPy_EyeAim_" + suffix + ".translateY",
                         start_aim[suffix] + offset)
            cmds.setAttr("ctrlEye_" + suffix + ".blink", blink)
        rows = {}
        for side, faces in areas.items():
            conflicts = []
            for face in faces:
                if mesh.getPolygonNormal(face, om.MSpace.kWorld).z <= .05:
                    continue
                if any(mesh.getFaceVertexNormal(face, vertex,
                       om.MSpace.kWorld).z < -.05
                       for vertex in mesh.getPolygonVertices(face)):
                    conflicts.append(face)
            rows[side] = {"area_faces": len(faces),
                          "front_faces_with_back_corner": len(conflicts),
                          "face_ids": conflicts}
        poses[label] = rows
    result = {"scene": scene.name, "down_cm": down_cm, "poses": poses}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print({label: {side: row["front_faces_with_back_corner"]
                   for side, row in sides.items()}
           for label, sides in poses.items()}, flush=True)


if __name__ == "__main__":
    main()
