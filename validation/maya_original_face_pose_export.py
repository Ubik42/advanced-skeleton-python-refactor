"""Export open and blink poses from an unmodified original ADV Maya scene."""
from __future__ import annotations

from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om


def main() -> None:
    scene = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    names = dict(zip(("head", "right-eye", "left-eye"), sys.argv[3:6]))
    if len(names) != 3:
        raise ValueError("需要头部、右眼和左眼三个原版网格名称")
    aim_dx = float(sys.argv[6]) if len(sys.argv) > 6 else 0.
    aim_dy = float(sys.argv[7]) if len(sys.argv) > 7 else 0.
    output.mkdir(parents=True, exist_ok=True)
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    meshes = {}
    for label, name in names.items():
        selection = om.MSelectionList()
        selection.add(name)
        mesh = om.MFnMesh(selection.getDagPath(0))
        faces = [mesh.getPolygonVertices(index)
                 for index in range(mesh.numPolygons)]
        meshes[label] = (mesh, faces)
    cmds.currentTime(1, edit=True)
    initial = {side + axis: cmds.getAttr(
        "ctrlEye_" + side + ".translate" + axis)
        for side in ("R", "L") for axis in "XY"}
    for label, blink in (("open", 0), ("blink", 10)):
        for key, value in initial.items():
            cmds.setAttr("ctrlEye_" + key[0] + ".translate" + key[1],
                         value + (aim_dx if key[1] == "X" else aim_dy))
        for control in ("ctrlEye_R", "ctrlEye_L"):
            cmds.setAttr(control + ".blink", blink)
        for mesh_label, (mesh, faces) in meshes.items():
            points = mesh.getPoints(om.MSpace.kWorld)
            path = output / (label + "-" + mesh_label + ".obj")
            with path.open("w", encoding="ascii") as stream:
                for point in points:
                    stream.write(f"v {point.x:.9f} {point.y:.9f} {point.z:.9f}\n")
                for face in faces:
                    stream.write("f " + " ".join(str(index + 1)
                                for index in face) + "\n")
            print(label, mesh_label, mesh.numVertices,
                  mesh.numPolygons, path, flush=True)


if __name__ == "__main__":
    main()
