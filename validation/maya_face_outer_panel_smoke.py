"""Exercise the Outer blink controls in Maya's offscreen Qt panel."""
from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide2 import QtWidgets
from adv_py.product.maya_panel import create_panel
from product_maya_panel_offscreen import FakeController


class OuterController(FakeController):
    def __init__(self):
        super().__init__()
        self.outer_offsets = {("Right", "upper"): (.01, -.02, .03)}

    def face_outer_blink_read(self, namespace, side, arc):
        return self.outer_offsets.get((side, arc), (0., 0., 0.))

    def face_outer_blink_apply(self, namespace, side, arc, offset):
        self.outer_offsets[(side, arc)] = offset
        return offset


def main() -> None:
    app = QtWidgets.QApplication([])
    controller = OuterController()
    panel = create_panel(controller)
    panel.roles.setCurrentRow(1)
    assert panel._namespace() == "hero"
    assert "右上" in panel._face_outer_blink_read()
    assert tuple(field.value() for field in panel.face_outer_offsets) == (
        .01, -.02, .03)
    panel.face_outer_offsets[1].setValue(-.04)
    assert "右上" in panel._face_outer_blink_apply()
    assert controller.outer_offsets[("Right", "upper")] == (
        .01, -.04, .03)
    panel.face_outer_side.setCurrentIndex(1)
    try:
        panel._face_outer_blink_apply()
    except ValueError as error:
        assert "先读取" in str(error)
    else:
        raise AssertionError("Changing eyes retained the previous edit")
    assert "左上" in panel._face_outer_blink_read()
    panel.close()
    app.processEvents()
    print("Outer blink panel read/edit/selection: OK", flush=True)


if __name__ == "__main__":
    main()
