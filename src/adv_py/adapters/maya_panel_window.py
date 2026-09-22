"""Native Maya window ownership for the product panel."""
from __future__ import annotations


def attach_to_maya_window(panel) -> None:
    from maya import OpenMayaUI
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance

    main_window = OpenMayaUI.MQtUtil.mainWindow()
    if main_window:
        panel.setParent(wrapInstance(int(main_window), QtWidgets.QWidget),
                        QtCore.Qt.Window)
