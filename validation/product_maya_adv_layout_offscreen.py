"""Check the original-style entry hierarchy and its detail routing."""
from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide2 import QtGui, QtWidgets
from adv_py.product.maya_adv_layout import ADV_OPERATIONS, ADV_SECTIONS, create_adv_panel
from product_maya_panel_offscreen import FakeController


def main() -> None:
    app = QtWidgets.QApplication([])
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.is_file():
        QtGui.QFontDatabase.addApplicationFont(str(font))
    panel = create_adv_panel(FakeController())
    panel.show()
    assert [section for section, _ in ADV_SECTIONS] == [
        "Preparation", "Body", "Face", "Pose", "Tools", "Display",
        "Optimize", "Updates", "Publish", "Export", "Demo", "About"]
    assert len(panel.section_buttons) == 12 + sum(len(children)
                                                 for _, children in ADV_SECTIONS)
    assert set(panel.operation_buttons) == {
        (section, subsection, label)
        for (section, subsection), entries in ADV_OPERATIONS.items()
        for label, _, _ in entries}
    panel.section_buttons[("Body", None)].click()
    panel.section_buttons[("Body", "Fit")].click()
    app.processEvents()
    panel.operation_buttons[("Body", "Fit", "导出当前 Fit")].click()
    assert panel.detail.tabs.currentIndex() == 0
    assert not panel.detail.tabs.tabBar().isVisible()
    assert panel.detail.windowTitle().endswith("Body / Fit")
    panel.section_buttons[("Face", None)].click()
    panel.section_buttons[("Face", "Build")].click()
    panel.operation_buttons[("Face", "Build", "构建面部控制")].click()
    assert panel.detail.tabs.currentIndex() == 3
    assert panel.detail.windowTitle().endswith("Face / Build")
    panel.section_buttons[("Body", "Control Curves")].click()
    panel.operation_buttons[("Body", "Control Curves",
                             "设置控制曲线颜色")].click()
    assert panel.detail.tabs.currentIndex() == 0
    assert panel.detail.windowTitle().endswith("Body / Control Curves")
    panel.section_buttons[("Body", "Control Orient")].click()
    panel.operation_buttons[("Body", "Control Orient",
                             "设置控制器局部轴")].click()
    assert panel.detail.tabs.currentIndex() == 0
    assert panel.detail.windowTitle().endswith("Body / Control Orient")
    panel.operation_buttons[("Body", "Control Orient",
                             "分离全部控制器")].click()
    panel.operation_buttons[("Body", "Control Orient",
                             "重新附着全部控制器")].click()
    panel.section_buttons[("Pose", None)].click()
    panel.section_buttons[("Pose", "Driving Systems")].click()
    panel.operation_buttons[("Pose", "Driving Systems", "转换脊柱模式")].click()
    assert panel.detail.tabs.currentIndex() == 2
    assert panel.detail.windowTitle().endswith("Pose / Driving Systems")
    panel.section_buttons[("Publish", None)].click()
    panel.operation_buttons[("Publish", None, "准备并烘焙发布骨架")].click()
    assert panel.detail.tabs.currentIndex() == 5
    assert panel.detail.windowTitle().endswith("Publish")
    panel.detail.close()
    app.processEvents()
    panel.operation_buttons[("Body", "Fit", "导出当前 Fit")].click()
    assert panel.detail.tabs.currentIndex() == 0
    panel.close()
    panel.detail.close()
    app.processEvents()
    print("AdvancedSkeleton-style hierarchy and detail routing: OK")


if __name__ == "__main__":
    main()
