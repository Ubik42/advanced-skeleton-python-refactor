"""Build three eyelid Fit layers from distinct rings on one face mesh."""
from __future__ import annotations

from collections import defaultdict
from math import hypot
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om

from adv_py.adapters.maya_face_pre import MayaFacePreHost
from adv_py.application.face_pre import EyeLidLayer
from adv_py.product.maya_panel_controller import MayaPanelController


def ring_edges(mesh):
    selection = om.MSelectionList()
    selection.add(mesh)
    fn = om.MFnMesh(selection.getDagPath(0))
    points = [fn.getPoint(index, om.MSpace.kWorld)
              for index in range(fn.numVertices)]
    groups = defaultdict(set)
    for index, point in enumerate(points):
        radius = hypot(point.x + .8, point.y - 3.1)
        groups[(round(radius, 4), round(point.z, 4))].add(index)
    rings = []
    for (radius, _), vertices in groups.items():
        edges = tuple(index for index in range(fn.numEdges)
            if set(fn.getEdgeVertices(index)).issubset(vertices))
        if len(edges) == 16:
            rings.append((radius, edges))
    rings.sort(reverse=True)
    unique = []
    for radius, edges in rings:
        if not unique or abs(radius - unique[-1][0]) > 1e-4:
            unique.append((radius, edges))
    assert len(unique) >= 3, unique
    return (unique[0][1], unique[len(unique)//2][1], unique[-1][1])


def main():
    with TemporaryDirectory(prefix="advpy-eyelid-") as folder:
        scene = Path(folder) / "eyelid-fit.mb"
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.select(clear=True)
        head = cmds.joint(name="Head_M", position=(0, 3, 0))
        mesh = cmds.polyTorus(name="FaceMesh", radius=.45,
                              sectionRadius=.08, subdivisionsAxis=16,
                              subdivisionsHeight=8,
                              constructionHistory=False)[0]
        cmds.xform(mesh, rotation=(90, 0, 0), worldSpace=True)
        cmds.xform(mesh, translation=(-.8, 3.1, 1.1), worldSpace=True)
        controller = MayaPanelController()
        cmds.select(mesh + ".f[0:31]", replace=True)
        controller.face_pre_record_mask(":")
        cmds.select(mesh, replace=True)
        controller.face_pre_record_objects(":", "Face", head)
        cmds.select(mesh, replace=True)
        controller.face_pre_record_objects(":", "AllHead", head)
        eye = cmds.polySphere(name="EyeRight", radius=.31,
                              subdivisionsX=8, subdivisionsY=8,
                              constructionHistory=False)[0]
        cmds.xform(eye, translation=(-.8, 3.1, 1.1), worldSpace=True)
        controller.face_fit_eye_ball(":", "|EyeRight", head)
        rings = ring_edges("|FaceMesh")
        cmds.select([f"{mesh}.e[{index}]" for index in rings[0][:-1]],
                    replace=True)
        try:
            controller.face_fit_eye_lid(":", "Outer")
        except ValueError:
            pass
        else:
            raise AssertionError("An open eyelid ring must be rejected")
        assert not cmds.objExists("FaceFitEyeLidOuter")
        for layer, edges in zip(("Outer", "Main", "Inner"), rings):
            cmds.select([f"{mesh}.e[{index}]" for index in edges],
                        replace=True)
            upper, lower = controller.face_fit_eye_lid(":", layer)
            for path in (upper, lower):
                assert cmds.objExists(path)
            for prefix in ("upper", "lower"):
                tube = prefix + "EyeLidCylinder" + layer
                assert cmds.objExists(tube)
                assert cmds.listRelatives(tube, shapes=True,
                                          type="nurbsSurface")
                curve = upper if prefix == "upper" else lower
                curve_box = cmds.exactWorldBoundingBox(curve)
                tube_box = cmds.exactWorldBoundingBox(tube)
                assert max(abs(a - b) for a, b in zip(curve_box, tube_box)) < .01
            upper_points = [cmds.pointPosition(upper + f".cv[{index}]",
                                               world=True)
                            for index in range(1,
                                int(cmds.getAttr(upper + ".spans")))]
            lower_points = [cmds.pointPosition(lower + f".cv[{index}]",
                                               world=True)
                            for index in range(1,
                                int(cmds.getAttr(lower + ".spans")))]
            assert sum(point[1] for point in upper_points) / len(upper_points) > (
                sum(point[1] for point in lower_points) / len(lower_points))
            cmds.undoInfo(stateWithoutFlush=False)
            assert controller.face_fit_eye_lid_reselect(":", layer) == len(edges)
            cmds.undoInfo(stateWithoutFlush=True)
        cmds.undo()
        assert not cmds.objExists("FaceFitEyeLidInner")
        cmds.redo()
        assert cmds.objExists("FaceFitEyeLidInner")
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(scene), open=True, force=True,
                  executeScriptNodes=False)
        host = MayaFacePreHost()
        for layer in EyeLidLayer:
            assert all(cmds.objExists(path)
                for path in host.read_eye_lid_fit(layer))
            assert host.select_eye_lid_fit(layer) == 16
        assert len(cmds.ls(type="skinCluster") or []) == 1
        print("Face EyeLid Outer/Main/Inner Maya smoke: OK", flush=True)


if __name__ == "__main__":
    main()
