"""Build independent asymmetric right/left EyeBall and EyeLid Fit layers."""
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
from adv_py.application.face_pre import EyeLidLayer, FaceSide
from adv_py.product.maya_panel_controller import MayaPanelController


def rings(mesh: str, center_x: float, axis_count: int):
    selected = om.MSelectionList()
    selected.add(mesh)
    fn = om.MFnMesh(selected.getDagPath(0))
    groups = defaultdict(set)
    for index in range(fn.numVertices):
        point = fn.getPoint(index, om.MSpace.kWorld)
        if abs(point.x - center_x) > .75:
            continue
        radius = hypot(point.x - center_x, point.y - 3.1)
        groups[(round(radius, 4), round(point.z, 4))].add(index)
    found = []
    for (radius, _), vertices in groups.items():
        edges = tuple(index for index in range(fn.numEdges)
                      if set(fn.getEdgeVertices(index)).issubset(vertices))
        if len(edges) == axis_count:
            found.append((radius, edges))
    found.sort(reverse=True)
    unique = []
    for radius, edges in found:
        if not unique or abs(radius - unique[-1][0]) > 1e-4:
            unique.append((radius, edges))
    assert len(unique) >= 3, unique
    return (unique[0][1], unique[len(unique) // 2][1], unique[-1][1])


def torus(name: str, center_x: float, radius: float, section: float,
          divisions: int):
    mesh = cmds.polyTorus(name=name, radius=radius, sectionRadius=section,
                          subdivisionsAxis=divisions, subdivisionsHeight=8,
                          constructionHistory=False)[0]
    cmds.xform(mesh, rotation=(90, 0, 0), worldSpace=True)
    cmds.xform(mesh, translation=(center_x, 3.1, 1.1), worldSpace=True)
    return mesh


def build_lids(controller, mesh: str, edge_rings, side: str):
    for layer, edges in zip(("Outer", "Main", "Inner"), edge_rings):
        corners = []
        if side == "Left" and layer != "Outer":
            selected = om.MSelectionList()
            selected.add(mesh)
            fn = om.MFnMesh(selected.getDagPath(0))
            vertices = {vertex for index in edges
                        for vertex in fn.getEdgeVertices(index)}
            by_x = sorted(vertices, key=lambda vertex:
                fn.getPoint(vertex, om.MSpace.kWorld).x)
            corners = ([by_x[1]] if layer == "Inner"
                       else [by_x[-2], by_x[1]])
        cmds.select([f"{mesh}.e[{index}]" for index in edges]
                    + [f"{mesh}.vtx[{index}]" for index in corners],
                    replace=True)
        upper, lower = controller.face_fit_eye_lid(":", layer)
        suffix = "Left" if side == "Left" else ""
        assert upper.endswith(f"upperEyeLid{layer}Curve{suffix}")
        assert lower.endswith(f"lowerEyeLid{layer}Curve{suffix}")
        if corners:
            expected = cmds.pointPosition(f"{mesh}.vtx[{corners[-1]}]",
                                          world=True)
            start = cmds.pointPosition(upper + ".cv[0]", world=True)
            assert max(abs(a-b) for a, b in zip(start, expected)) < 1e-5
        if layer != "Inner" or side != "Left":
            cmds.undoInfo(stateWithoutFlush=False)
            assert controller.face_fit_eye_lid_reselect(":", layer) == len(edges)
            cmds.undoInfo(stateWithoutFlush=True)


def main():
    with TemporaryDirectory(prefix="advpy-eyelid-left-") as folder:
        scene = Path(folder) / "asymmetric-eyes.mb"
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.select(clear=True)
        head = cmds.joint(name="Head_M", position=(0, 3, 0))
        right = torus("RightFace", -.82, .45, .08, 16)
        left = torus("LeftFace", .91, .52, .10, 20)
        mesh = cmds.polyUnite(right, left, name="FaceMesh",
                              constructionHistory=False)[0]
        controller = MayaPanelController()
        cmds.select(mesh + ".f[0:31]", replace=True)
        controller.face_pre_record_mask(":")
        cmds.select(mesh, replace=True)
        controller.face_pre_record_objects(":", "Face", head)
        cmds.select(mesh, replace=True)
        controller.face_pre_record_objects(":", "AllHead", head)
        right_eye = cmds.polySphere(name="EyeRight", radius=.31,
                                    constructionHistory=False)[0]
        cmds.xform(right_eye, translation=(-.82, 3.1, 1.1), worldSpace=True)
        right_fit = controller.face_fit_eye_ball(":", "|EyeRight", head)
        assert right_fit.endswith("|FitEyeBall")
        build_lids(controller, mesh, rings("|FaceMesh", -.82, 16), "Right")
        right_area = MayaFacePreHost().read_eye_lid_area()
        assert controller.face_fit_switch_side(":", "Left") == "Left"
        assert not cmds.getAttr("FaceFitEyeLidOuter.visibility")
        cmds.undo()
        assert MayaFacePreHost().active_face_side() is FaceSide.RIGHT
        assert cmds.getAttr("FaceFitEyeLidOuter.visibility")
        cmds.redo()
        assert MayaFacePreHost().active_face_side() is FaceSide.LEFT
        left_eye = cmds.polySphere(name="EyeLeft", radius=.34,
                                   constructionHistory=False)[0]
        cmds.xform(left_eye, translation=(.91, 3.1, 1.1), worldSpace=True)
        left_fit = controller.face_fit_eye_ball(":", "|EyeLeft", head)
        assert left_fit.endswith("|FitEyeBallLeft")
        assert cmds.xform(left_fit, query=True, worldSpace=True,
                          translation=True)[0] > .8
        assert cmds.getAttr("FaceFitSkeleton.NonSym")
        assert cmds.getAttr("FaceFitSkeleton.NonSymSide") == "Left"
        left_rings = rings("|FaceMesh", .91, 20)
        build_lids(controller, mesh, left_rings, "Left")
        host = MayaFacePreHost()
        area, preview = host.read_eye_lid_area()
        assert area.endswith("|EyeLidInnerAreaMeshLeft")
        assert preview.endswith("|EyeLidInnerAreaMeshExtrudeLeft")
        assert int(cmds.polyEvaluate(area, face=True)) > 0
        assert cmds.getAttr("FaceFitEyeLidOuterLeft.visibility")
        cmds.undo()
        assert not cmds.objExists("FaceFitEyeLidInnerLeft")
        cmds.redo()
        assert all(cmds.objExists(path) for path in host.read_eye_lid_area())
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(scene), open=True, force=True,
                  executeScriptNodes=False)
        host = MayaFacePreHost()
        assert host.active_face_side() is FaceSide.LEFT
        assert host.read_eye_ball_fit().endswith("|FitEyeBallLeft")
        assert host.select_eye_lid_fit(EyeLidLayer.INNER) == 20
        assert host.read_eye_lid_area() != right_area
        assert controller.face_fit_switch_side(":", "Right") == "Right"
        assert host.read_eye_ball_fit().endswith("|FitEyeBall")
        assert host.select_eye_lid_fit(EyeLidLayer.INNER) == 16
        assert all(cmds.objExists(path) for path in host.read_eye_lid_area())
        assert cmds.getAttr("FaceFitEyeLidOuter.visibility")
        assert not cmds.getAttr("FaceFitEyeLidOuterLeft.visibility")
        assert controller.face_fit_switch_side(":", "Left") == "Left"
        assert host.select_eye_lid_fit(EyeLidLayer.INNER) == 20
        print("Asymmetric right/left EyeBall and EyeLid Fit Maya smoke: OK",
              flush=True)


if __name__ == "__main__":
    main()
