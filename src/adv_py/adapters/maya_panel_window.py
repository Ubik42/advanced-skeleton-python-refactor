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


def attach_to_maya_dock(panel) -> str:
    """Mount the compact navigation panel in Maya's left workspace area."""
    from maya import cmds, OpenMayaUI
    from shiboken2 import getCppPointer

    name = "AdvPyWorkspaceControl"
    if cmds.workspaceControl(name, exists=True):
        cmds.deleteUI(name, control=True)
    cmds.workspaceControl(name, label="AdvancedSkeleton Python",
                          dockToControl=("ToolBox", "left"),
                          initialWidth=400, minimumWidth=330,
                          retain=False)
    pointer = OpenMayaUI.MQtUtil.findControl(name)
    if not pointer:
        raise RuntimeError("无法取得 Maya 工作区容器")
    OpenMayaUI.MQtUtil.addWidgetToMayaLayout(
        int(getCppPointer(panel)[0]), int(pointer))
    cmds.workspaceControl(name, edit=True, restore=True, visible=True)
    cmds.workspaceControl(name, edit=True, **{"raise": True})
    return name
