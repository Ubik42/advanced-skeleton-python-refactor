"""Click the original-layout Delta Mush entry in a visible Maya session."""
from __future__ import annotations

import json
from pathlib import Path
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore, QtWidgets

from adv_py.product.maya_adv_layout import create_adv_panel


def schedule(scene: str, output_directory: str) -> None:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        data = {"asset": Path(scene).name}
        try:
            cmds.file(scene, open=True, force=True, executeScriptNodes=False)
            mesh = "|Group|Geometry|model:geo|model:body"
            if not cmds.objExists(mesh):
                raise RuntimeError("公开 Sam 主体网格不存在")
            cmds.setAttr("FKShoulder_R.rotateX", 25.)
            model = (cmds.getPanel(type="modelPanel") or [None])[0]
            if model is None:
                raise RuntimeError("Maya 没有可见模型视窗")
            cmds.modelEditor(model, edit=True,
                             displayAppearance="smoothShaded",
                             displayTextures=False, wireframeOnShaded=False,
                             grid=False, joints=False, nurbsCurves=False,
                             selectionHiliteDisplay=False)
            cmds.lookThru(model, "front")
            cmds.select(mesh, replace=True)
            cmds.setFocus(model)
            cmds.viewFit(fitFactor=.8)
            cmds.setAttr("front.orthographicWidth",
                         cmds.getAttr("front.orthographicWidth") * 1.5)
            cmds.select(clear=True)
            before = cmds.playblast(
                format="image", compression="png", viewer=False,
                offScreen=True, showOrnaments=False,
                startTime=cmds.currentTime(query=True),
                endTime=cmds.currentTime(query=True),
                widthHeight=(1280, 900), percent=100,
                filename=str(output / "sam-delta-before"),
                forceOverwrite=True)

            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Body", None)].click()
            panel.section_buttons[("Body", "Deform DeltaMush")].click()
            button = panel.operation_buttons[(
                "Body", "Deform DeltaMush", "应用 Delta Mush")]
            button.click()
            detail = panel.detail
            QtWidgets.QApplication.processEvents()
            data["entry_visible"] = (panel.isVisible()
                and detail.isVisible() and button.isVisible())
            cmds.select(mesh, replace=True)
            action = next(widget for widget in detail.findChildren(
                QtWidgets.QPushButton)
                if widget.text() == "应用 Delta Mush")
            action.click()
            QtWidgets.QApplication.processEvents()
            data["status_text"] = detail.status.toPlainText()
            data["node_created"] = cmds.objExists(
                "model:AdvPy_DeltaMush_body")
            detail.grab().save(str(output / "sam-delta-panel.png"))
            panel.grab().save(str(output / "sam-delta-navigation.png"))
            cmds.select(clear=True)
            after = cmds.playblast(
                format="image", compression="png", viewer=False,
                offScreen=True, showOrnaments=False,
                startTime=cmds.currentTime(query=True),
                endTime=cmds.currentTime(query=True),
                widthHeight=(1280, 900), percent=100,
                filename=str(output / "sam-delta-after"),
                forceOverwrite=True)
            data["before_image"] = str(before)
            data["after_image"] = str(after)
            harden_nav = panel.operation_buttons[(
                "Body", "Deform DeltaMush", "硬化权重")]
            data["harden_entry_visible"] = harden_nav.isVisible()
            cmds.select(mesh, replace=True)
            harden_action = next(widget for widget in detail.findChildren(
                QtWidgets.QPushButton) if widget.text() == "硬化权重")
            harden_action.click()
            QtWidgets.QApplication.processEvents()
            data["harden_status_text"] = detail.status.toPlainText()
            detail.grab().save(str(output / "sam-delta-harden-panel.png"))
            data["passed"] = (data["entry_visible"]
                and data["node_created"]
                and data["harden_entry_visible"]
                and "已硬化 1 个网格" in data["harden_status_text"]
                and "已为 1 个网格应用 Delta Mush" in data["status_text"]
                and bool(list(output.glob("sam-delta-before.*.png")))
                and bool(list(output.glob("sam-delta-after.*.png"))))
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            (output / "sam-delta-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
