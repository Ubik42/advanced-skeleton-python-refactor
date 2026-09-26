"""Click Preparation Skin, All and One Joint Prop in Maya."""
from __future__ import annotations

import json
from pathlib import Path
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore, QtWidgets

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
            model = (output / "prop.mb").resolve()
            rig = (output / "prop-rig.mb").resolve()
            cmds.file(new=True, force=True)
            cmds.polyCube(name="BodyMesh", width=2, height=2, depth=2)
            cmds.polySphere(name="AccessoryMesh", radius=.25)
            cmds.move(0, 1.5, 0, "AccessoryMesh")
            cmds.file(rename=str(model))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(new=True, force=True)
            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Preparation", None)].click()
            panel.section_buttons[("Preparation", "Rig")].click()
            panel.operation_buttons[("Preparation", "Rig", "引用模型文件")].click()
            detail = panel.detail
            detail.preparation_model_source.setText(str(model))
            button = next(b for b in detail.findChildren(QtWidgets.QPushButton)
                          if b.text() == "引用模型文件")
            button.click()
            data["reference_status"] = detail.status.toPlainText()
            panel.operation_buttons[("Preparation", "Rig", "Skin")].click()
            cmds.select("model:BodyMesh", replace=True)
            detail.findChild(QtWidgets.QPushButton, "AdvPyPrepRecordSkin").click()
            data["skin_status"] = detail.status.toPlainText()
            panel.operation_buttons[("Preparation", "Rig", "All")].click()
            cmds.select("model:BodyMesh", "model:AccessoryMesh", replace=True)
            detail.findChild(QtWidgets.QPushButton, "AdvPyPrepRecordAll").click()
            data["all_status"] = detail.status.toPlainText()
            panel.operation_buttons[("Preparation", "Rig",
                                     "创建单关节道具绑定")].click()
            button = next(b for b in detail.findChildren(QtWidgets.QPushButton)
                          if b.text() == "创建单关节道具绑定")
            button.click()
            data["build_status"] = detail.status.toPlainText()
            data["skin_count"] = len(cmds.ls(type="skinCluster") or [])
            data["root"] = cmds.objExists("|Group|Rig|Root_M")
            detail.grab().save(str(output / "one-joint-prop-panel.png"))
            cmds.file(rename=str(rig))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(str(rig), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_skin_count"] = len(cmds.ls(type="skinCluster") or [])
            data["reopen_referenced"] = cmds.referenceQuery(
                "model:BodyMesh", isNodeReferenced=True)
            data["passed"] = ("已引用" in data["reference_status"]
                and "已记录 Skin" in data["skin_status"]
                and "已记录 All" in data["all_status"]
                and "单关节道具已构建" in data["build_status"]
                and data["skin_count"] == data["reopen_skin_count"] == 2
                and data["root"] and data["reopen_referenced"]
                and "modal_error" not in data)
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            dialogs.stop()
            (output / "one-joint-prop-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
