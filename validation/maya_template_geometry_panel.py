"""Real graphical Maya panel buttons for the complete template geometry chain."""
import sys,json,traceback
from template_geometry_fixture import ROOT,setup
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/template-geometry-panel'
def main():
    from maya import cmds as c
    from PySide2 import QtCore,QtWidgets,QtTest
    from adv_py.product.maya_panel import create_panel
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running'}
    panel=None
    try:
        setup('normal');panel=create_panel();panel.show();QtWidgets.QApplication.processEvents()
        def click(title,label):
            for fold in panel.findChildren(QtWidgets.QToolButton):
                if fold.text() in ('Body','Geometry / Skeleton','Geometry / Muscular','Geometry / Mannequin') and fold.isCheckable():fold.setChecked(True)
            QtWidgets.QApplication.processEvents()
            groups=[group for group in panel.findChildren(QtWidgets.QGroupBox) if group.title()==title.split(' · ',1)[-1]]
            assert len(groups)==1,(title,len(groups))
            buttons=[button for button in groups[0].findChildren(QtWidgets.QPushButton) if button.text()==label]
            assert len(buttons)==1,(title,label)
            button=buttons[0]
            for area in panel.findChildren(QtWidgets.QScrollArea):
                if area.isAncestorOf(button):area.ensureWidgetVisible(button)
            QtWidgets.QApplication.processEvents();assert button.isVisible(),title
            QtTest.QTest.mouseClick(button,QtCore.Qt.LeftButton);QtWidgets.QApplication.processEvents()
            return panel.status.toPlainText()
        for title,group in [('00 · Mannequin','MannequinGeometry'),('00 · Skeleton','SkeletonGeometry'),('00 · Muscular','MuscularGeometry')]:
            message=click(title,'Create');assert c.objExists(group),(title,message)
            report[group]={'create':message}
        panel.grab().save(str(OUT/'panel.png'))
        for title,group in [('00 · Muscular','MuscularGeometry'),('00 · Skeleton','SkeletonGeometry'),('00 · Mannequin','MannequinGeometry')]:
            message=click(title,'Delete');assert not c.objExists(group),(title,message)
            report[group]['delete']=message;c.undo();assert c.objExists(group);c.redo();assert not c.objExists(group)
        report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
        if panel:panel.close()
        c.quit(force=True)

