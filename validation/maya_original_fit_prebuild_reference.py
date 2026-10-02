"""Capture untouched native manual Fit prebuild frames and branch choices."""
from pathlib import Path
import json,traceback
ROOT=Path(__file__).resolve().parents[1]

def main():
    from maya import cmds,mel
    output=ROOT/'validation/results/original-fit-prebuild-reference.json'
    report=dict(status='running')
    try:
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        cmds.optionVar(intValue=('asHaveRanThisVersion',1));cmds.optionVar(intValue=('asDock',0))
        mel.eval('AdvancedSkeleton;')
        cmds.file(str(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'),open=True,force=True,executeScriptNodes=False)
        def capture():
            return {node:dict(matrix=cmds.xform(node,q=True,ws=True,m=True),child=mel.eval('asRlaChild '+node),
                attributes={attr:cmds.getAttr(node+'.'+attr) for attr in ('worldOrient','worldOrientUp','worldOrientForward','freeOrient','flipOrient') if cmds.objExists(node+'.'+attr)})
                for node in cmds.listRelatives('FitSkeleton',ad=True,type='joint') or []}
        report['before']=capture()
        cmds.createNode('transform',name='asFitModeManualUpdateFromBuild')
        mel.eval('asFitModeManualUpdate;')
        report['after']=capture();report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.quit(force=True)
