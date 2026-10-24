"""Inspect the single source-ordered business panel without desktop windows."""
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PySide2 import QtGui, QtWidgets
from adv_py.product.maya_adv_layout import ADV_OPERATIONS, ADV_SECTIONS
from adv_py.product.maya_panel import create_panel
from product_maya_panel_offscreen import FakeController

def main():
    app = QtWidgets.QApplication([])
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.is_file():
        QtGui.QFontDatabase.addApplicationFont(str(font))
    panel = create_panel(FakeController())
    panel.show()
    assert not hasattr(panel, 'detail')
    assert panel.namespace_selector.model() is panel.roles.model()
    before = list(panel.controller.calls)
    count = 0
    for (section, subsection), entries in ADV_OPERATIONS.items():
        for label, _, group in entries:
            panel.open_original_section(group, section, subsection)
            app.processEvents()
            category, child, widget = panel._original_section_routes[group]
            assert category.isChecked() and child.isChecked()
            assert widget.isVisible(), (section, subsection, label)
            count += 1
    assert panel.controller.calls == before
    actual = [button.text() for button in panel.findChildren(QtWidgets.QToolButton)
              if button.objectName() == 'AdvPyCategory']
    assert actual == [name for name, _ in ADV_SECTIONS]
    panel.close()
    app.processEvents()
    print(f'Single business panel: {count} routes, source order, no mutations: OK')

if __name__ == '__main__':
    main()
