"""Collect unchanged MEL Mannequin geometry on a native Body."""
import json,traceback
from template_geometry_fixture import ROOT,setup,sample,poses
OUT=ROOT/'validation/results/original-mannequin-reference'
def main():
    from maya import cmds as c,mel
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running'}
    try:
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0))
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";');mel.eval('AdvancedSkeleton;')
        for mode in ('normal','alternate_axes','retained_shader'):
            setup(mode);mel.eval('asCreateMannequin;')
            row={'meshes':sample('MannequinGeometry'),'height':c.getAttr('Main.height')};report[mode]=row
            assert row['meshes']
            if mode=='normal':row['poses']=poses('MannequinGeometry')
            c.file(rename=str(OUT/(mode+'.mb')));c.file(save=True,type='mayaBinary',force=True)
            mel.eval('asDeleteMannequin;');assert not c.objExists('MannequinGeometry')
            row['remaining_shader']=c.objExists('shaderMannequin') and c.objExists('shaderMannequinSG')
        report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'reference.json').write_text(json.dumps(report),encoding='utf8');c.quit(force=True)
