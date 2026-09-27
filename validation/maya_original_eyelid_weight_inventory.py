"""Read original ADV eyelid influence masses on Fit rings and the full head."""
from __future__ import annotations

from array import array
import json
from pathlib import Path
import re
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaAnim as oma


_EDGE = re.compile(r"\.e\[(\d+)\]$")
_LID = re.compile(r"^(upper|lower)Lid(Main|Outer)\d+_(R|L)$")


def main() -> None:
    scene = Path(sys.argv[1]).resolve()
    head_name = sys.argv[2]
    output = Path(sys.argv[3]).resolve()
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    selection = om.MSelectionList()
    selection.add(head_name)
    dag = selection.getDagPath(0)
    mesh = om.MFnMesh(dag)
    skins = [node for node in cmds.listHistory(head_name) or []
             if cmds.nodeType(node) == "skinCluster"]
    if len(skins) != 1:
        raise RuntimeError("原版头部 Skin 数量不唯一：" + repr(skins))
    selection = om.MSelectionList()
    selection.add(skins[0])
    skin = oma.MFnSkinCluster(selection.getDependNode(0))
    component_fn = om.MFnSingleIndexedComponent()
    component = component_fn.create(om.MFn.kMeshVertComponent)
    component_fn.addElements(range(mesh.numVertices))
    weights, width = skin.getWeights(dag, component)
    weights = array("d", weights)
    influences = [path.fullPathName().rsplit("|", 1)[-1]
                  for path in skin.influenceObjects()]
    if width != len(influences):
        raise RuntimeError("原版 Skin 权重维度不符")
    group_names = ("upperMain", "lowerMain", "upperOuter",
                   "lowerOuter", "other")

    def grouped_weights(vertex: int) -> dict[str, float]:
        grouped = dict.fromkeys(group_names, 0.)
        for index, name in enumerate(influences):
            mass = weights[vertex * width + index]
            match = _LID.fullmatch(name)
            key = (match.group(1) + match.group(2)
                   if match and match.group(3) == "R" else "other")
            grouped[key] += mass
        return grouped

    groups = {}
    for layer in ("Outer", "Main", "Inner"):
        holder = (cmds.ls("FaceFitEyeLid" + layer,
                          long=True, type="transform") or [None])[0]
        if holder is None:
            raise RuntimeError("原版 Fit 缺失：" + layer)
        record = cmds.getAttr(holder + ".selection") or ""
        edges = [int(match.group(1)) for item in record.split()
                 if (match := _EDGE.search(item))]
        vertices = sorted({vertex for edge in edges
                           for vertex in mesh.getEdgeVertices(edge)})
        rows = []
        for vertex in vertices:
            point = mesh.getPoint(vertex, om.MSpace.kWorld)
            grouped = grouped_weights(vertex)
            rows.append({"vertex": vertex,
                         "position_cm": [float(point[axis])
                                         for axis in range(3)],
                         "weights": {key: round(value, 6)
                                     for key, value in grouped.items()},
                         "top_influences": sorted((
                             (influences[index], round(
                                 weights[vertex * width + index], 6))
                             for index in range(width)
                             if weights[vertex * width + index] > .001),
                             key=lambda row: -row[1])[:5]})
        groups[layer] = rows
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"scene": scene.name, "skin": skins[0],
                                  "influence_count": width,
                                  "rings": groups,
                                  "group_names": group_names,
                                  "vertex_group_weights": [
                                      [round(value, 6) for value in
                                       grouped_weights(vertex).values()]
                                      for vertex in range(mesh.numVertices)]},
                                 ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Original ADV eyelid weights:", scene.name, skins[0],
          {layer: {key: round(sum(row["weights"][key] for row in rows)
                              / len(rows), 4)
                   for key in rows[0]["weights"]}
           for layer, rows in groups.items()}, flush=True)


if __name__ == "__main__":
    main()
