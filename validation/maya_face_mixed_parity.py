"""Accept loading only the inspected local native nodeCast plugin for this run."""
from pathlib import Path
import json

def load_project_native_plugin():
    from maya import cmds as c
    from PySide2 import QtCore, QtWidgets
    import maya_face_conversion_parity as suite
    folder = Path(__file__).resolve().parents[1] / 'src/adv_py/maya_plugins'
    plugins = tuple((folder / name).resolve() for name in ('native_node_cast.py', 'skin_bulk.py'))
    log = suite.OUTPUT / 'plugin-dialog.json'
    def inspect_dialog():
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if not widget.isVisible() or not isinstance(widget, QtWidgets.QDialog):
                continue
            labels = [label.text() for label in widget.findChildren(QtWidgets.QLabel)]
            buttons = widget.findChildren(QtWidgets.QAbstractButton)
            text = '\n'.join(labels)
            if not any(plugin.name in text and plugin.parent.as_posix() in text.replace('\\', '/') for plugin in plugins):
                continue
            log.write_text(json.dumps({'title': widget.windowTitle(), 'labels': labels,
                                      'buttons': [button.text() for button in buttons]}, indent=2), encoding='utf8')
            # Allow one load only. Keep persistent location trust unchecked.
            for checkbox in widget.findChildren(QtWidgets.QCheckBox):
                if 'apply to all' in checkbox.text().replace('&', '').lower():
                    checkbox.setChecked(False)
            for button in buttons:
                if button.text().replace('&', '').lower() in ('allow', 'load', 'allow once'):
                    button.click()
                    return
    timer = QtCore.QTimer()
    timer.timeout.connect(inspect_dialog)
    timer.start(500)
    try:
        suite.OUTPUT.mkdir(parents=True, exist_ok=True)
        for plugin in plugins:
            if not c.pluginInfo(str(plugin), query=True, loaded=True):
                c.loadPlugin(str(plugin), quiet=True)
    finally:
        timer.stop()


def main(*, standalone=False, quit_on_finish=True):
    import maya_face_conversion_parity as suite
    load_project_native_plugin()
    suite.main(modes=('mixed',), standalone=standalone, quit_on_finish=quit_on_finish)
