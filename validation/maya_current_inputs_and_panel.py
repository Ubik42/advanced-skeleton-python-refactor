"""Read saved RP inputs and inspect all product routes in one owned Maya session."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'validation/results/current-inputs-and-panel'


def main(*, standalone=False, quit_on_finish=True):
    if standalone:
        raise ValueError('This validation requires a Maya Qt session')
    from maya import cmds
    from PySide2 import QtCore, QtWidgets
    from adv_py.product.maya_adv_layout import ADV_OPERATIONS, ADV_SECTIONS
    from adv_py.product.maya_panel import show_panel
    from maya_rp_input_compare import main as inspect_inputs

    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', pid=os.getpid(),
                  scope='Saved RP input inspection and actual Maya Qt routing; no business acceptance')
    panels = []
    def settle_dock():
        # Yield to Maya and the owned-window supervisor after dock layouts
        # resize the main window. Capture the settled viewport, not its startup
        # or intermediate size.
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(700, loop.quit)
        loop.exec_()
    try:
        if os.environ.get('ADV_PANEL_ONLY') == '1':
            scene = Path(os.environ['ADV_RP_PYTHON_SCENE'])
            cmds.file(str(scene), open=True, force=True, executeScriptNodes=False)
            report['scope'] = 'Actual Maya Qt routes and captures; saved RP inspection not repeated'
        else:
            assert inspect_inputs(standalone=False, quit_on_finish=False) == 0
        before = set(cmds.ls(uuid=True))
        detail = show_panel()
        panels.append(detail)
        assert cmds.workspaceControl('AdvPyWorkspaceControl', exists=True)
        assert detail.namespace_selector.model() is detail.roles.model()
        assert not hasattr(detail, 'detail'), 'Launcher opened a second workbench'
        # Render real Maya Qt widgets without displaying or activating another
        # top-level window over the user's desktop.
        detail.resize(425, 750)
        from adv_py.core.source_fit_labels import SOURCE_FIT_UI_LABELS
        from adv_py.core.source_fit_attributes import SOURCE_FIT_ATTRIBUTE_TYPES, source_fit_attribute_help
        assert tuple(detail.fit_source_label.itemText(i) for i in range(
            detail.fit_source_label.count())) == SOURCE_FIT_UI_LABELS
        for i, attribute in enumerate(SOURCE_FIT_ATTRIBUTE_TYPES):
            detail.fit_source_attribute.setCurrentIndex(i)
            assert detail.fit_source_attribute_help.text() == source_fit_attribute_help(attribute)
        count = 0
        conditional_hidden = []
        for (section, subsection), entries in ADV_OPERATIONS.items():
            for label, _, group in entries:
                detail.open_original_section(group, section, subsection)
                QtWidgets.QApplication.processEvents()
                category, child, widget = detail._original_section_routes[group]
                assert category.isChecked() and child.isChecked()
                if group == '03a · Face Skin Layers' and not detail.controller.face_skin_layers_visible(detail._namespace()):
                    assert not widget.isVisible()
                    conditional_hidden.append(label)
                else:
                    assert widget.isVisible(), (section, subsection, label, group)
                count += 1
        assert before == set(cmds.ls(uuid=True)), 'Navigation changed the rig graph'
        # Exercise the actual label buttons, not only the controller API.
        detail.open_original_section('02 · Fit 编辑', 'Body', 'Edit')
        fixture_namespace = 'PanelLabelFixture'
        assert not cmds.namespace(exists=fixture_namespace)
        cmds.namespace(add=fixture_namespace)
        joints = [cmds.createNode('joint', name=fixture_namespace + ':' + leaf)
                  for leaf in ('First', 'Second')]
        nonjoint = cmds.createNode('transform', name=fixture_namespace + ':NotJoint')
        try:
            cmds.select(joints + [nonjoint], replace=True)
            detail.fit_source_label.setCurrentText('Hand')
            group = detail._original_section_routes['02 · Fit 编辑'][2]
            buttons = {button.text(): button for button in group.findChildren(QtWidgets.QPushButton)}
            buttons['Add'].click()
            assert all(cmds.getAttr(joint + '.drawLabel') and cmds.getAttr(joint + '.type') == 12 for joint in joints)
            buttons['Remove'].click()
            assert all(not cmds.getAttr(joint + '.drawLabel') and cmds.getAttr(joint + '.type') == 12 for joint in joints)
        finally:
            cmds.delete(joints + [nonjoint])
            cmds.namespace(removeNamespace=fixture_namespace)
        assert before == set(cmds.ls(uuid=True)), 'Label fixture cleanup changed the saved rig'
        report['label_buttons'] = 'Add/Remove passed on two joints plus a transform'
        settle_dock()
        report['panel_geometry'] = dict(width=detail.width(), height=detail.height(),
            minimum_hint_height=detail.minimumSizeHint().height(),
            window_height=detail.window().height(),
            scroll_height=detail.operation_page.height())
        import ctypes
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                        ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
        user32 = ctypes.windll.user32
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
        handle = wintypes.HWND(int(detail.window().winId()))
        rect, monitor = wintypes.RECT(), MonitorInfo()
        monitor.size = ctypes.sizeof(monitor)
        assert user32.GetWindowRect(handle, ctypes.byref(rect))
        assert user32.GetMonitorInfoW(user32.MonitorFromWindow(handle, 2), ctypes.byref(monitor))
        lower = monitor.work.top + (monitor.work.bottom - monitor.work.top + 1) // 2
        report['native_window_bounds'] = [rect.left, rect.top, rect.right, rect.bottom]
        report['secondary_lower_bounds'] = [monitor.work.left, lower, monitor.work.right, monitor.work.bottom]
        assert not monitor.flags & 1, 'Test window is on the primary monitor'
        assert (rect.left >= monitor.work.left and rect.top >= lower and
                rect.right <= monitor.work.right and rect.bottom <= monitor.work.bottom), 'Test window escaped secondary lower area'
        for section, subsection, group in (
                ('Preparation','Settings','00 · Settings'),
                ('Body','Deform option2','00 · SkinCage'),
                ('Body','Control Mesh','10A · Control Mesh'),
                ('Body','Edit','02 · Fit 编辑'),
                ('Face','Layers','03a · Face Skin Layers'),
                ('Face','Build ...','03O · 原版眼部绑定与修形')):
            detail.open_original_section(group, section, subsection)
            QtWidgets.QApplication.processEvents()
            settle_dock()
            filename = section + '-' + subsection.replace(' ', '_').replace('.', '') + '.png'
            assert detail.grab().save(str(OUT / filename))
        report.update(status='passed', routes=count, sections=len(ADV_SECTIONS),
                      unchanged_scene_nodes=True, public_launcher=True,
                      conditional_hidden=conditional_hidden,
                      label_menu_count=len(SOURCE_FIT_UI_LABELS),
                      attribute_help_count=len(SOURCE_FIT_ATTRIBUTE_TYPES),
                      render='Actual Maya docked business panel on secondary lower area')
    except Exception:
        report.update(status='failed', traceback=traceback.format_exc())
    finally:
        for panel in panels:
            panel.close()
            panel.deleteLater()
        (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        completion = os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:
            Path(completion).write_text(json.dumps(dict(pid=os.getpid(), status=report['status'])), encoding='utf-8')
        if quit_on_finish:
            cmds.evalDeferred('quit -force')
    return 0 if report['status'] == 'passed' else 1
