"""Export evaluated Face mesh positions at two frames as local static OBJ files."""
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
    output.mkdir(parents=True, exist_ok=True)
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    selection = om.MSelectionList()
    selection.add("head")
    mesh = om.MFnMesh(selection.getDagPath(0))
    faces = [mesh.getPolygonVertices(index)
             for index in range(mesh.numPolygons)]
    for frame, label in ((1, "open"), (10, "blink")):
        cmds.currentTime(frame, edit=True)
        if frame == 10:
            cmds.setAttr("ctrlEye_R.blink", 10)
            cmds.setAttr("ctrlEye_L.blink", 10)
        points = mesh.getPoints(om.MSpace.kWorld)
        path = output / (label + "-head.obj")
        with path.open("w", encoding="ascii") as stream:
            for point in points:
                stream.write(f"v {point.x:.9f} {point.y:.9f} {point.z:.9f}\n")
            for face in faces:
                stream.write("f " + " ".join(str(index + 1)
                            for index in face) + "\n")
        print(label, mesh.numVertices, mesh.numPolygons, path, flush=True)


if __name__ == "__main__":
    main()
