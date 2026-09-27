"""Isolate the effect of original eyelid weights on a rebuilt Maya rig.

The original scene is read only. Its eyelid influence weights are mapped by
joint name; all remaining mass goes to the rebuilt Head joint. The result is
diagnostic and must not be used as a production binding workflow.
"""
from __future__ import annotations

from array import array
from pathlib import Path
import re
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaAnim as oma


_LID = re.compile(r"^((?:upper|lower)Lid(?:Main|Outer))(\d+)(_[RL])$")


def skin_data(mesh_name: str):
    mesh_names = cmds.ls(mesh_name, long=True, type="transform") or []
    if len(mesh_names) != 1:
        raise RuntimeError("头部网格不唯一：" + mesh_name)
    skins = [item for item in cmds.listHistory(mesh_names[0]) or []
             if cmds.nodeType(item) == "skinCluster"]
    if len(skins) != 1:
        raise RuntimeError("头部 Skin 不唯一：" + mesh_name)
    selection = om.MSelectionList()
    selection.add(skins[0])
    skin = oma.MFnSkinCluster(selection.getDependNode(0))
    selection = om.MSelectionList()
    selection.add(mesh_names[0])
    dag = selection.getDagPath(0)
    count = om.MFnMesh(dag).numVertices
    component_fn = om.MFnSingleIndexedComponent()
    component = component_fn.create(om.MFn.kMeshVertComponent)
    component_fn.addElements(range(count))
    weights, width = skin.getWeights(dag, component)
    names = [path.fullPathName().rsplit("|", 1)[-1]
             for path in skin.influenceObjects()]
    if len(names) != width:
        raise RuntimeError("Skin 影响关节数量不符")
    return skin, dag, component, count, names, array("d", weights)


def main() -> None:
    original, original_mesh, rebuilt, rebuilt_mesh, output = sys.argv[1:6]
    cmds.file(str(Path(original).resolve()), open=True, force=True,
              executeScriptNodes=False)
    (source_skin, source_dag, source_component, vertex_count,
     source_names, source_values) = skin_data(original_mesh)
    source_blend = source_skin.getBlendWeights(source_dag, source_component)
    skinning_method = cmds.getAttr(source_skin.name() + ".skinningMethod")
    cmds.file(str(Path(rebuilt).resolve()), open=True, force=True,
              executeScriptNodes=False)
    skin, dag, component, target_count, target_names, _ = skin_data(rebuilt_mesh)
    if vertex_count != target_count:
        raise RuntimeError("原版和重构头部顶点数不同")
    target_index = {name: index for index, name in enumerate(target_names)}
    head_index = target_index["Head_M"]
    source_lids = [(index, name) for index, name in enumerate(source_names)
                   if _LID.fullmatch(name)]
    remapped = {}
    for _, name in source_lids:
        if name in target_index:
            remapped[name] = name
            continue
        match = _LID.fullmatch(name)
        candidates = [(abs(int(_LID.fullmatch(item).group(2)) - int(match.group(2))),
                       item) for item in target_names
                      if _LID.fullmatch(item)
                      and _LID.fullmatch(item).group(1) == match.group(1)
                      and _LID.fullmatch(item).group(3) == match.group(3)]
        if not candidates:
            raise RuntimeError("重构绑定缺少原版眼睑关节：" + name)
        remapped[name] = min(candidates)[1]
    width = len(target_names)
    values = array("d", [0.] * (target_count * width))
    for vertex in range(target_count):
        mass = 0.
        for index, name in source_lids:
            weight = source_values[vertex * len(source_names) + index]
            values[vertex * width + target_index[remapped[name]]] += weight
            mass += weight
        values[vertex * width + head_index] = max(0., 1. - mass)
    skin.setWeights(dag, component, om.MIntArray(range(width)),
                    om.MDoubleArray(values), False)
    skin.setBlendWeights(dag, component, source_blend)
    cmds.setAttr(skin.name() + ".skinningMethod", skinning_method)
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmds.file(rename=str(output_path))
    cmds.file(save=True, type="mayaBinary", force=True)
    print("Mapped original eyelid weights:", len(source_lids), "joints,",
          target_count, "vertices,",
          sum(name != mapped for name, mapped in remapped.items()),
          "endpoint joints approximated, method", skinning_method,
          "blend vertices", sum(value > .5 for value in source_blend),
          flush=True)


if __name__ == "__main__":
    main()
