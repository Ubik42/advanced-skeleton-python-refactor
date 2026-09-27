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
from adv_py.application.face_pre import EyeLidLayer
from adv_py.product.maya_adv_layout import create_adv_panel
from adv_py.product.maya_panel_controller import MayaPanelController


def _rings(mesh):
    selection = om.MSelectionList()
    selection.add(mesh)
    fn = om.MFnMesh(selection.getDagPath(0))
    points = [fn.getPoint(index, om.MSpace.kWorld)
              for index in range(fn.numVertices)]
    groups = defaultdict(set)
    for index, point in enumerate(points):
        groups[(round(hypot(point.x + .8, point.y - 3.1), 4),
                round(point.z, 4))].add(index)
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
            face = cmds.polyTorus(name="FaceMesh", radius=.45,
                sectionRadius=.08, subdivisionsAxis=16,
                subdivisionsHeight=8, constructionHistory=False)[0]
            cmds.xform(face, rotation=(90, 0, 0), worldSpace=True)
            cmds.xform(face, translation=(-.8, 3.1, 1.1), worldSpace=True)
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
                cmds.select([f"{face}.e[{index}]" for index in edges],
                            replace=True)
                label = "EyeLid " + layer
                panel.operation_buttons[("Face", "Fit", label)].click()
                detail = panel.detail
                button = next(widget for widget in
                    detail.findChildren(QtWidgets.QPushButton)
                    if widget.text() == label)
                button.click()
                data[layer.lower() + "_status"] = detail.status.toPlainText()
            detail.grab().save(str(output / "face-eyelid-fit-panel.png"))
            panel.grab().save(str(output / "face-eyelid-fit-accordion.png"))
            cmds.select("FaceFitEyeLidOuter", "FaceFitEyeLidMain",
                        "FaceFitEyeLidInner", replace=True)
            guides = cmds.listRelatives("FaceFitSkeleton", shapes=True,
                                        fullPath=True) or []
            hidden = [node for node in (*guides, "FitEyeSphere")
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
            data["reopen_curves"] = all(
                all(cmds.objExists(path) for path in
                    host.read_eye_lid_fit(layer)) for layer in EyeLidLayer)
            data["passed"] = (all("已建立 EyeLid" in
                data[layer + "_status"] for layer in ("outer", "main", "inner"))
                and data["reopen_curves"] and "modal_error" not in data)
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
