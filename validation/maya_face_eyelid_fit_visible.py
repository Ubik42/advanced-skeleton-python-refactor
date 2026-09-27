"""Click the original-style Face / Fit eyelid rows in Maya GUI."""
from __future__ import annotations

from collections import defaultdict
import json
from math import hypot
from pathlib import Path
import traceback

from maya import cmds
import maya.utils
from maya.api import OpenMaya as om
from PySide2 import QtCore, QtWidgets

from adv_py.adapters.maya_face_pre import MayaFacePreHost
from adv_py.application.face_pre import EyeLidLayer, FaceSide
from adv_py.product.maya_adv_layout import create_adv_panel
from adv_py.product.maya_panel_controller import MayaPanelController


def _rings(mesh, center_x=-.8, axis_count=16):
    selection = om.MSelectionList()
    selection.add(mesh)
    fn = om.MFnMesh(selection.getDagPath(0))
    points = [fn.getPoint(index, om.MSpace.kWorld)
              for index in range(fn.numVertices)]
    groups = defaultdict(set)
    for index, point in enumerate(points):
        if abs(point.x - center_x) > .75:
            continue
        groups[(round(hypot(point.x - center_x, point.y - 3.1), 4),
                round(point.z, 4))].add(index)
    rings = []
    for (radius, _), vertices in groups.items():
        edges = tuple(index for index in range(fn.numEdges)
            if set(fn.getEdgeVertices(index)).issubset(vertices))
        if len(edges) == axis_count:
            rings.append((radius, edges))
    rings.sort(reverse=True)
    unique = []
    for radius, edges in rings:
        if not unique or abs(radius - unique[-1][0]) > 1e-4:
            unique.append((radius, edges))
    return (unique[0][1], unique[len(unique)//2][1], unique[-1][1])


def schedule(output_directory: str) -> None:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        data = {}
        dialogs = QtCore.QTimer()
        dialogs.setInterval(250)

        def handle_dialogs():
            for widget in QtWidgets.QApplication.topLevelWidgets():
                if isinstance(widget, QtWidgets.QMessageBox) and widget.isVisible():
                    data["modal_error"] = widget.text()
                    widget.reject()

        dialogs.timeout.connect(handle_dialogs)
        dialogs.start()
        try:
            cmds.file(new=True, force=True)
            cmds.select(clear=True)
            head = cmds.joint(name="Head_M", position=(0, 3, 0))
            right_face = cmds.polyTorus(name="RightFace", radius=.45,
                sectionRadius=.08, subdivisionsAxis=16,
                subdivisionsHeight=8, constructionHistory=False)[0]
            cmds.xform(right_face, rotation=(90, 0, 0), worldSpace=True)
            cmds.xform(right_face, translation=(-.8, 3.1, 1.1),
                       worldSpace=True)
            left_face = cmds.polyTorus(name="LeftFace", radius=.52,
                sectionRadius=.10, subdivisionsAxis=20,
                subdivisionsHeight=8, constructionHistory=False)[0]
            cmds.xform(left_face, rotation=(90, 0, 0), worldSpace=True)
            cmds.xform(left_face, translation=(.91, 3.1, 1.1),
                       worldSpace=True)
            face = cmds.polyUnite(right_face, left_face, name="FaceMesh",
                                  constructionHistory=False)[0]
            controller = MayaPanelController()
            cmds.select(face + ".f[0:31]", replace=True)
            controller.face_pre_record_mask(":")
            cmds.select(face, replace=True)
            controller.face_pre_record_objects(":", "Face", head)
            cmds.select(face, replace=True)
            controller.face_pre_record_objects(":", "AllHead", head)
            eye = cmds.polySphere(name="EyeRight", radius=.31,
                subdivisionsX=8, subdivisionsY=8,
                constructionHistory=False)[0]
            cmds.xform(eye, translation=(-.8, 3.1, 1.1), worldSpace=True)
            controller.face_fit_eye_ball(":", "|EyeRight", head)
            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Face", None)].click()
            panel.section_buttons[("Face", "Fit")].click()
            detail = None
            for layer, edges in zip(("Outer", "Main", "Inner"),
                                    _rings("|FaceMesh")):
                selection = om.MSelectionList()
                selection.add("|FaceMesh")
                fn = om.MFnMesh(selection.getDagPath(0))
                vertices = {vertex for index in edges
                            for vertex in fn.getEdgeVertices(index)}
                by_x = sorted(vertices,
                              key=lambda vertex: fn.getPoint(
                                  vertex, om.MSpace.kWorld).x)
                corners = [] if layer == "Outer" else (
                    [by_x[-2]] if layer == "Inner" else [by_x[1], by_x[-2]])
                cmds.select([f"{face}.e[{index}]" for index in edges]
                            + [f"{face}.vtx[{index}]" for index in corners],
                            replace=True)
                label = "EyeLid " + layer
                panel.operation_buttons[("Face", "Fit", label)].click()
                detail = panel.detail
                button = next(widget for widget in
                    detail.findChildren(QtWidgets.QPushButton)
                    if widget.text() == label)
                button.click()
                data[layer.lower() + "_status"] = detail.status.toPlainText()
                reselect = next(widget for widget in
                    detail.findChildren(QtWidgets.QPushButton)
                    if widget.text() == "重选 " + layer)
                reselect.click()
                data[layer.lower() + "_reselected_corners"] = len([
                    item for item in (cmds.ls(selection=True, flatten=True) or [])
                    if ".vtx[" in item])
            area, preview = MayaFacePreHost().read_eye_lid_area()
            data["inner_area_faces"] = int(cmds.polyEvaluate(area, face=True))
            data["inner_preview_faces"] = int(cmds.polyEvaluate(preview, face=True))
            panel.section_buttons[("Face", "Pre")].click()
            panel.operation_buttons[("Face", "Pre", "编辑左侧")].click()
            detail = panel.detail
            next(widget for widget in detail.findChildren(QtWidgets.QPushButton)
                 if widget.text() == "编辑左侧").click()
            data["left_side_status"] = detail.status.toPlainText()
            left_eye = cmds.polySphere(name="EyeLeft", radius=.34,
                subdivisionsX=8, subdivisionsY=8,
                constructionHistory=False)[0]
            cmds.xform(left_eye, translation=(.91, 3.1, 1.1), worldSpace=True)
            panel.section_buttons[("Face", "Fit")].click()
            panel.operation_buttons[("Face", "Fit", "建立 EyeBall Fit")].click()
            detail = panel.detail
            detail.face_fit_left_eye.setText("|EyeLeft")
            next(widget for widget in detail.findChildren(QtWidgets.QPushButton)
                 if widget.text() == "建立 EyeBall Fit").click()
            data["left_eye_status"] = detail.status.toPlainText()
            for layer, edges in zip(("Outer", "Main", "Inner"),
                                    _rings("|FaceMesh", .91, 20)):
                cmds.select([f"{face}.e[{index}]" for index in edges],
                            replace=True)
                label = "EyeLid " + layer
                panel.operation_buttons[("Face", "Fit", label)].click()
                detail = panel.detail
                next(widget for widget in detail.findChildren(
                    QtWidgets.QPushButton) if widget.text() == label).click()
                data["left_" + layer.lower() + "_status"] = (
                    detail.status.toPlainText())
            left_area, left_preview = MayaFacePreHost().read_eye_lid_area()
            data["left_area_faces"] = int(cmds.polyEvaluate(left_area, face=True))
            data["left_preview_faces"] = int(cmds.polyEvaluate(
                left_preview, face=True))
            detail.grab().save(str(output / "face-eyelid-fit-panel.png"))
            panel.grab().save(str(output / "face-eyelid-fit-accordion.png"))
            cmds.select("FaceFitEyeLidOuterLeft", "FaceFitEyeLidMainLeft",
                        "FaceFitEyeLidInnerLeft", replace=True)
            guides = cmds.listRelatives("FaceFitSkeleton", shapes=True,
                                        fullPath=True) or []
            hidden = [node for node in (*guides, "FitEyeSphere",
                                      "FitEyeSphereLeft")
                      if cmds.getAttr(node + ".visibility")]
            try:
                for node in hidden:
                    cmds.setAttr(node + ".visibility", False)
                cmds.viewFit()
                data["viewport_capture"] = cmds.playblast(
                    format="image", compression="png", viewer=False,
                    offScreen=True, showOrnaments=False, frame=1,
                    widthHeight=(960, 600), percent=100,
                    filename=str(output / "face-eyelid-viewport"),
                    forceOverwrite=True)
            except Exception as error:
                data["viewport_error"] = str(error)
            finally:
                for node in hidden:
                    cmds.setAttr(node + ".visibility", True)
            scene = output / "face-eyelid-fit.mb"
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(str(scene), open=True, force=True,
                      executeScriptNodes=False)
            host = MayaFacePreHost()
            reopened_panel = create_adv_panel()
            reopened_panel.section_buttons[("Face", None)].click()
            reopened_panel.section_buttons[("Face", "Pre")].click()
            reopened_panel.operation_buttons[("Face", "Pre", "编辑左侧")].click()
            data["reopen_side_label"] = (
                reopened_panel.detail.face_fit_side_status.text())
            data["reopen_curves"] = all(
                all(cmds.objExists(path) for path in
                    host.read_eye_lid_fit(layer, side))
                for layer in EyeLidLayer for side in FaceSide)
            data["reopen_area"] = all(cmds.objExists(path)
                for side in FaceSide for path in host.read_eye_lid_area(side))
            data["passed"] = (all("已建立 EyeLid" in
                data[layer + "_status"] for layer in ("outer", "main", "inner"))
                and [data[layer + "_reselected_corners"] for layer in
                     ("outer", "main", "inner")] == [0, 2, 1]
                and 0 < data["inner_area_faces"] < data["inner_preview_faces"]
                and all("已建立 EyeLid" in data["left_" + layer + "_status"]
                        for layer in ("outer", "main", "inner"))
                and "Left" in data["left_eye_status"]
                and 0 < data["left_area_faces"] < data["left_preview_faces"]
                and data["reopen_side_label"] == "Fit 编辑侧：左侧"
                and data["reopen_curves"] and data["reopen_area"]
                and "modal_error" not in data)
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            dialogs.stop()
            (output / "face-eyelid-fit-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
