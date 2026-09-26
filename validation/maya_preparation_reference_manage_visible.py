"""Click reference reload, replacement, and removal in Maya's window."""
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
            first = (output / "first.ma").resolve()
            second = (output / "second.ma").resolve()
            rig = (output / "rig.ma").resolve()
            cmds.file(new=True, force=True)
            cmds.polyCube(name="BodyMesh")
            cmds.file(rename=str(first))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.polyCube(name="BodyMesh")
            cmds.polySphere(name="HatMesh")
            cmds.file(rename=str(second))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(rename=str(rig))
            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Preparation", None)].click()
            panel.section_buttons[("Preparation", "Rig")].click()
            panel.operation_buttons[("Preparation", "Rig", "引用模型文件")].click()
            detail = panel.detail

            def click(label):
                button = next(button for button in detail.findChildren(
                    QtWidgets.QPushButton) if button.text() == label)
                assert button.isVisible(), label
                button.click()
                QtWidgets.QApplication.processEvents()
                return detail.status.toPlainText()

            detail.preparation_model_source.setText(str(first))
            data["reference"] = click("引用模型文件")
            assert cmds.objExists("model:BodyMesh")
            data["reload"] = click("重新加载模型引用")
            detail.preparation_model_source.setText(str(second))
            data["replace"] = click("替换模型引用文件")
            assert cmds.objExists("model:HatMesh")
            detail.grab().save(str(output / "replacement-panel.png"))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(str(rig), open=True, force=True,
                      executeScriptNodes=False)
            assert cmds.objExists("model:HatMesh")
            data["remove"] = click("移除模型引用")
            data["removed"] = not cmds.objExists("model:BodyMesh")
            detail.grab().save(str(output / "removal-panel.png"))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(str(rig), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_removed"] = not cmds.objExists("model:BodyMesh")
            data["passed"] = ("已引用" in data["reference"]
                and "已重新加载" in data["reload"]
                and "已替换" in data["replace"]
                and "已移除" in data["remove"]
                and data["removed"] and data["reopen_removed"]
                and "modal_error" not in data)
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            dialogs.stop()
            (output / "reference-manage-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
