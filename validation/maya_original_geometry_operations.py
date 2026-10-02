"""Untouched ADV Boolean/Warp/CutUp procedures with actual dialog clicks."""
from pathlib import Path
import json,traceback
from geometry_operations_fixture import ROOT,setup_fixture,snapshot,poses
OUT=ROOT/'validation/results/original-geometry-operations'


def main():
    from maya import cmds as c,mel
    from PySide2 import QtCore,QtWidgets
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running'}
    timer=QtCore.QTimer()
    def accept_source_dialog():
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if widget.isVisible() and widget.windowTitle() in ('Boolean','Warp'):
                for button in widget.findChildren(QtWidgets.QPushButton):
                    if button.text().replace('&','')=='OK':button.click();return
    timer.timeout.connect(accept_source_dialog);timer.start(100)
    try:
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0))
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";');mel.eval('AdvancedSkeleton;')
        for kind,proc,group in [('boolean','asCreateBoolean','BoolGeometry'),('warp','asCreateWarp','WarpGeometry'),('cut_up','asCreateCutUp','CutUpGeometry')]:
            setup_fixture(kind);mel.eval(proc+';')
            first=snapshot(group);assert first,kind
            report[kind]={'first':first,'poses':poses(group),'source_visibility':c.getAttr('SourceGeometry.visibility')}
            c.select('SourceGeometry',replace=True)
            try:mel.eval(proc+';')
            except RuntimeError:report[kind]['append_error']=traceback.format_exc()
            report[kind]['appended']=snapshot(group)
            c.file(rename=str(OUT/(kind+'.mb')));c.file(save=True,type='mayaBinary',force=True)
            mel.eval({'boolean':'asDeleteBoolean','warp':'asDeleteWarp','cut_up':'asDeleteCutUp'}[kind]+';')
            assert not c.objExists(group);report[kind]['delete']=True
        report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        timer.stop();(OUT/'reference.json').write_text(json.dumps(report,indent=2),encoding='utf8');c.quit(force=True)
