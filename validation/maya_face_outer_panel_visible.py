"""Click Main/Outer blink edit rows in Maya GUI and capture the panel."""
from __future__ import annotations

import json
import os
from pathlib import Path
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore, QtWidgets

from adv_py.product.maya_adv_layout import create_adv_panel


def schedule() -> None:
    scene = Path(os.environ["ADV_PY_SCENE"]).resolve()
    output = Path(os.environ["ADV_PY_OUTPUT"]).resolve()
    output.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        report = {}
        try:
            cmds.file(str(scene), open=True, force=True,
                      executeScriptNodes=False)
            panel = create_adv_panel()
            panel.show()
            panel.section_buttons[("Face", None)].click()
            panel.section_buttons[("Face", "Build")].click()
            panel.operation_buttons[("Face", "Build",
                                     "读取眼睑修形")].click()
            detail = panel.detail
            detail.resize(1080, 900)
            detail.show()
            detail.roles.setCurrentRow(0)
            detail._face_outer_blink_read()
            before = tuple(field.value() for field in
                           detail.face_outer_offsets)
            detail.face_outer_offsets[0].setValue(before[0] + .01)
            detail._face_outer_blink_apply()
            after = tuple(field.value() for field in detail.face_outer_offsets)
            assert abs(cmds.getAttr(
                "ctrlUpperEyeLidOuter_R.blinkOffsetX") - after[0]) < 1e-8
            detail.face_lid_layer.setCurrentIndex(1)
            detail._face_outer_blink_read()
            main_before = tuple(field.value() for field in
                                detail.face_outer_offsets)
            detail.face_outer_offsets[2].setValue(main_before[2] + .01)
            detail._face_outer_blink_apply()
            main_after = tuple(field.value() for field in
                               detail.face_outer_offsets)
            assert abs(cmds.getAttr(
                "ctrlUpperEyeLid_R.blinkOffsetZ") - main_after[2]) < 1e-8
            content = detail.tabs.widget(3)
            content.verticalScrollBar().setValue(
                content.verticalScrollBar().maximum())
            QtWidgets.QApplication.processEvents()
            screenshot = output / "outer-blink-panel.png"
            assert detail.grab().save(str(screenshot))
            report = {"outer_before": before, "outer_after": after,
                      "main_before": main_before, "main_after": main_after,
                      "screenshot": str(screenshot), "passed": True}
            panel.close()
            detail.close()
        except BaseException:
            report = {"error": traceback.format_exc(), "passed": False}
        finally:
            (output / "outer-blink-panel.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
