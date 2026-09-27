"""Inventory original blink-driven Skin influences outside segmented eyelids.

Read-only source inspection. Output stays in ignored validation/results.
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
from maya.api import OpenMayaAnim as oma


_SEGMENT = re.compile(r"^(upper|lower)Lid(Main|Outer)\d+_[RL]$")


def main() -> None:
    scene, head_name, output = Path(sys.argv[1]).resolve(), sys.argv[2], Path(sys.argv[3]).resolve()
    cmds.file(str(scene), open=True, force=True, executeScriptNodes=False)
    cmds.currentTime(1, edit=True)
    selection = om.MSelectionList()
    selection.add(head_name)
    dag = selection.getDagPath(0)
    vertex_count = om.MFnMesh(dag).numVertices
    skins = [node for node in cmds.listHistory(head_name) or ()
             if cmds.nodeType(node) == "skinCluster"]
    if len(skins) != 1:
        raise RuntimeError("头部网格需要唯一 Skin")
    selection = om.MSelectionList()
    selection.add(skins[0])
    skin = oma.MFnSkinCluster(selection.getDependNode(0))
    component_fn = om.MFnSingleIndexedComponent()
    component = component_fn.create(om.MFn.kMeshVertComponent)
    component_fn.addElements(range(vertex_count))
    weights, width = skin.getWeights(dag, component)
    joints = [path.fullPathName() for path in skin.influenceObjects()]
    if len(joints) != width:
        raise RuntimeError("Skin 影响关节维度不符")

    def pose(blink: float) -> list[list[float]]:
        for side in ("R", "L"):
            control = "ctrlEye_" + side
            if not cmds.objExists(control + ".blink"):
                raise RuntimeError("缺少原版眨眼控制：" + control)
            cmds.setAttr(control + ".blink", blink)
        return [cmds.xform(joint, query=True, worldSpace=True, matrix=True)
                for joint in joints]

    opened = pose(0.)
    closed = pose(10.)
    rows = []
    for index, (joint, first, last) in enumerate(zip(joints, opened, closed)):
        name = joint.rsplit("|", 1)[-1]
        if _SEGMENT.fullmatch(name):
            continue
        matrix_delta = max(abs(a-b) for a, b in zip(first, last))
        if matrix_delta <= 1e-6:
            continue
        masses = [float(weights[vertex * width + index])
                  for vertex in range(vertex_count)]
        weighted = [vertex for vertex, mass in enumerate(masses)
                    if mass > 1e-6]
        if not weighted:
            continue
        source = cmds.connectionInfo(joint + ".translateX",
                                     sourceFromDestination=True)
        rows.append({
            "joint": name,
            "parent": (cmds.listRelatives(joint, parent=True) or [None])[0],
            "translate_x_source": source or None,
            "world_matrix_max_delta": round(matrix_delta, 7),
            "open_position_cm": [round(value, 7) for value in first[12:15]],
            "closed_position_cm": [round(value, 7) for value in last[12:15]],
            "weighted_vertex_count": len(weighted),
            "total_weight": round(sum(masses), 7),
            "maximum_weight": round(max(masses), 7),
        })
    rows.sort(key=lambda row: -row["total_weight"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"source_name": scene.name,
                                  "head": head_name,
                                  "vertex_count": vertex_count,
                                  "non_segmented_moving_influences": rows},
                                 ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Blink-driven non-segmented Skin influences:",
          [(row["joint"], row["weighted_vertex_count"],
            row["total_weight"]) for row in rows], flush=True)


if __name__ == "__main__":
    main()
