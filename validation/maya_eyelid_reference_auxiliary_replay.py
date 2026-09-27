"""Isolate original lower-Outer cheek influence on a rebuilt eyelid rig.

This diagnostic copies source Skin weights by identical vertex index. It is
not a generic binding or migration path and must not be used on other topology.
Both input scenes are opened read-only; the result is a new ignored scene.
"""
from __future__ import annotations

from array import array
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaAnim as oma


def skin_data(mesh_name: str):
    selection = om.MSelectionList()
    selection.add(mesh_name)
    dag = selection.getDagPath(0)
    mesh = om.MFnMesh(dag)
    skins = [node for node in cmds.listHistory(mesh_name) or ()
             if cmds.nodeType(node) == "skinCluster"]
    if len(skins) != 1:
        raise RuntimeError("头部网格需要唯一 Skin")
    selection = om.MSelectionList()
    selection.add(skins[0])
    skin = oma.MFnSkinCluster(selection.getDependNode(0))
    component_fn = om.MFnSingleIndexedComponent()
    component = component_fn.create(om.MFn.kMeshVertComponent)
    component_fn.addElements(range(mesh.numVertices))
    values, width = skin.getWeights(dag, component)
    names = [path.fullPathName().rsplit("|", 1)[-1]
             for path in skin.influenceObjects()]
    return (skin, dag, component, mesh, array("d", values),
            width, names)


def main() -> None:
    original, original_mesh, rebuilt, rebuilt_mesh, output = sys.argv[1:6]
    output_path = Path(output).resolve()
    if output_path in (Path(original).resolve(), Path(rebuilt).resolve()):
        raise ValueError("输出不能覆盖输入场景")
    cmds.file(str(Path(original).resolve()), open=True, force=True,
              executeScriptNodes=False)
    cmds.currentTime(1, edit=True)
    for side in ("R", "L"):
        cmds.setAttr("ctrlEye_" + side + ".blink", 0.)
    (_, _, _, source_mesh, source_values,
     source_width, source_names) = skin_data(original_mesh)
    source_count = source_mesh.numVertices
    source_points = [tuple(float(point[axis]) for axis in range(3))
                     for point in source_mesh.getPoints(om.MSpace.kWorld)]
    source = {}
    for side in ("R", "L"):
        name = "lowerLidOuterJoint_" + side
        if name not in source_names:
            raise RuntimeError("原版缺少外围眼睑影响关节：" + name)
        index = source_names.index(name)
        source[side] = {
            "pivot": cmds.xform(name, query=True, worldSpace=True,
                                translation=True),
            "weights": [(vertex, float(source_values[
                vertex * source_width + index]))
                for vertex in range(source_count)
                if source_values[vertex * source_width + index] > 1e-6],
        }
    cmds.file(str(Path(rebuilt).resolve()), open=True, force=True,
              executeScriptNodes=False)
    cmds.currentTime(1, edit=True)
    for side in ("R", "L"):
        cmds.setAttr("ctrlEye_" + side + ".blink", 0.)
    (skin, dag, component, mesh, values, width,
     names) = skin_data(rebuilt_mesh)
    if mesh.numVertices != source_count:
        raise RuntimeError("原版与重构头部顶点数不同")
    points = mesh.getPoints(om.MSpace.kWorld)
    maximum = max(max(abs(a[axis]-b[axis]) for axis in range(3))
                  for a, b in zip(source_points, points))
    if maximum > 1e-4:
        raise RuntimeError(f"原版与重构头部张眼位置不一致：{maximum}")
    for side in ("R", "L"):
        name = "lowerLidOuterJoint_" + side
        if cmds.objExists(name):
            raise RuntimeError("重构场景已存在外围关节：" + name)
        cmds.select(clear=True)
        joint = cmds.joint(name=name)
        joint = cmds.parent(joint, "FaceJoint_M", absolute=True)[0]
        pivot = source[side]["pivot"]
        cmds.xform(joint, worldSpace=True, translation=pivot)
        addition = cmds.createNode("plusMinusAverage", name=name + "MotionSum")
        cmds.setAttr(addition + ".input3D[0]", *pivot, type="double3")
        cmds.connectAttr("ctrlLowerEyeLidOuter_" + side +
                         "MotionSum.output3D", addition + ".input3D[1]")
        cmds.connectAttr(addition + ".output3D", joint + ".translate")
        cmds.skinCluster(skin.name(), edit=True,
                         addInfluence=joint, weight=0.)
    skin, dag, component, mesh, values, width, names = skin_data(rebuilt_mesh)
    for side in ("R", "L"):
        index = names.index("lowerLidOuterJoint_" + side)
        for vertex, mass in source[side]["weights"]:
            for influence in range(width):
                values[vertex * width + influence] *= 1. - mass
            values[vertex * width + index] = mass
    skin.setWeights(dag, component, om.MIntArray(range(width)),
                    om.MDoubleArray(values), False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmds.file(rename=str(output_path))
    cmds.file(save=True, type="mayaBinary", force=True)
    print("Replayed original lower Outer influences:",
          {side: len(source[side]["weights"]) for side in source},
          "bind-position maximum", maximum, flush=True)


if __name__ == "__main__":
    main()
