"""Click Face Pre eye selection and build in a visible Maya session."""
from __future__ import annotations

import json
from pathlib import Path
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore, QtWidgets

from adv_py.adapters.maya_face_eye import MayaFaceEyeHost
from adv_py.adapters.maya_preparation_reference import MayaPreparationReferenceHost
from adv_py.application import (BuildBodyCharacterRig,
    BuildOrientedBodySkeleton, BuildVariableBodySourceFit,
    CreateFitSkeleton, RegisterBodyCharacter)
from adv_py.application.preparation_reference import ReferencePreparationModel
from adv_py.core.variable_body_fit import variable_axial_description
from adv_py.product.maya_adv_layout import create_adv_panel


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
            host = MayaFaceEyeHost()
            CreateFitSkeleton(host).apply()
            BuildVariableBodySourceFit(host).apply(spine_segments=4)
            BuildOrientedBodySkeleton(host).apply()
            rig = BuildBodyCharacterRig(host).apply(
                include_torso=True, include_spine_ik=True,
                include_control_spaces=True,
                axial_description=variable_axial_description(4))
            registration = RegisterBodyCharacter(host).apply(rig)
            head = next(joint.path for joint in registration.body
                        if joint.path.rsplit("|", 1)[-1] == "Head_M")
            head_pos = cmds.xform(head, query=True, worldSpace=True,
                                  translation=True)
            for name, side in (("EyeRight", -1), ("EyeLeft", 1)):
                cmds.polySphere(name=name, radius=.25, subdivisionsX=8,
                                subdivisionsY=6, constructionHistory=False)
                cmds.xform(name, worldSpace=True, translation=(
                    head_pos[0] + side * .55, head_pos[1] + .1,
                    head_pos[2] + .75))
            model = (output / "eyes.mb").resolve()
            scene = (output / "eye-rig.mb").resolve()
            cmds.select("EyeRight", "EyeLeft", replace=True)
            cmds.file(str(model), exportSelected=True, type="mayaBinary", force=True)
            cmds.delete("EyeRight", "EyeLeft")
            ReferencePreparationModel(MayaPreparationReferenceHost()).execute(model)
            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Face", None)].click()
            panel.section_buttons[("Face", "Pre")].click()
            panel.operation_buttons[("Face", "Pre", "记录所选右眼")].click()
            detail = panel.detail
            detail.face_eye_head.setText(head)
            cmds.select("model:EyeRight", replace=True)
            button = next(b for b in detail.findChildren(QtWidgets.QPushButton)
                          if b.text() == "记录所选右眼")
            button.click()
            data["right_status"] = detail.status.toPlainText()
            cmds.select("model:EyeLeft", replace=True)
            button = next(b for b in detail.findChildren(QtWidgets.QPushButton)
                          if b.text() == "记录所选左眼")
            button.click()
            data["left_status"] = detail.status.toPlainText()
            panel.operation_buttons[("Face", "Pre",
                                     "建立双眼控制与蒙皮")].click()
            button = next(b for b in detail.findChildren(QtWidgets.QPushButton)
                          if b.text() == "建立双眼控制与蒙皮")
            button.click()
            data["build_status"] = detail.status.toPlainText()
            data["skin_count"] = len(cmds.ls("AdvPy_EyeSkin_*",
                                             type="skinCluster") or [])
            data["body_registered"] = any(entry.namespace == ":" and
                entry.registered for entry in detail.controller.characters())
            detail.grab().save(str(output / "face-eyes-panel.png"))
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(str(scene), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_skin_count"] = len(cmds.ls("AdvPy_EyeSkin_*",
                type="skinCluster") or [])
            data["reopen_controls"] = all(cmds.objExists(name) for name in (
                "AdvPy_EyeAim", "AdvPy_EyeAim_R", "AdvPy_EyeAim_L"))
            data["passed"] = ("已记录右眼" in data["right_status"]
                and "已记录左眼" in data["left_status"]
                and "双眼控制已构建" in data["build_status"]
                and data["skin_count"] == data["reopen_skin_count"] == 2
                and data["body_registered"] and data["reopen_controls"]
                and "modal_error" not in data)
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            dialogs.stop()
            (output / "face-eyes-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
