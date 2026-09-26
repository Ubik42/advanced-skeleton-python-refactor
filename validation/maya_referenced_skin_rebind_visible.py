"""Click export and rebind entries in a real Maya window."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore, QtWidgets

from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
from adv_py.product.maya_adv_layout import create_adv_panel


def schedule(rig_source: str, output_directory: str) -> None:
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
            model = (output / "model.mb").resolve()
            rig = (output / "rig.mb").resolve()
            asset = (output / "source.skin-surface.json").resolve()
            shutil.copy2(Path(rig_source).parent / "model.mb", model)
            cmds.file(rig_source, open=True, force=True,
                      executeScriptNodes=False)
            reference = cmds.referenceQuery("model:BodyMesh", referenceNode=True)
            cmds.file(str(model), loadReference=reference)
            cmds.file(rename=str(rig))
            cmds.file(save=True, type="mayaBinary", force=True)

            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Body", None)].click()
            panel.section_buttons[("Body", "Deform option1")].click()
            panel.operation_buttons[("Body", "Deform option1",
                                     "导出网格与权重")].click()
            detail = panel.detail
            detail.surface_source_skin.setText("AdvPy_BodySkin")
            detail.surface_source_mesh.setText("|model:BodyMesh")
            detail.surface_asset_out.setText(str(asset))
            export = next(button for button in detail.findChildren(
                QtWidgets.QPushButton) if button.text() == "导出网格与权重")
            export.click()
            data["export_status"] = detail.status.toPlainText()
            data["asset_exists"] = asset.is_file()
            assert data["asset_exists"]

            cmds.file(str(model), open=True, force=True,
                      executeScriptNodes=False)
            cmds.polySubdivideFacet("BodyMesh.f[0]", divisions=1)
            cmds.delete("BodyMesh", constructionHistory=True)
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(str(rig), open=True, force=True,
                      executeScriptNodes=False)
            detail.refresh_characters()
            panel.operation_buttons[("Body", "Deform option1",
                "引用模型改拓扑后重绑并转移")].click()
            detail.surface_mode.setCurrentIndex(1)
            detail.surface_asset_in.setText(str(asset))
            detail.surface_target_skin.setText("AdvPy_BodySkin")
            detail.surface_target_mesh.setText("|model:BodyMesh")
            rebind = next(button for button in detail.findChildren(
                QtWidgets.QPushButton)
                if button.text() == "引用模型改拓扑后重绑并转移")
            rebind.click()
            data["rebind_status"] = detail.status.toPlainText()
            data["vertices"] = MayaDenseSkinHost().capture_dense_skin(
                "AdvPy_BodySkin").vertex_count
            detail.grab().save(str(output / "rebind-panel.png"))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(str(rig), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_vertices"] = MayaDenseSkinHost().capture_dense_skin(
                "AdvPy_BodySkin").vertex_count
            data["passed"] = ("已封装" in data["export_status"]
                and "已重绑并转移" in data["rebind_status"]
                and data["vertices"] == data["reopen_vertices"] == 18156
                and "modal_error" not in data)
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            dialogs.stop()
            (output / "rebind-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
