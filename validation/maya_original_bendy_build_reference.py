"""Build the untouched original Bendy rig in Maya GUI and retain reference data."""
from pathlib import Path
import sys,json,hashlib,traceback
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'local/adv_6_925/AdvancedSkeleton.mel'
REFERENCE=Path('D:/3D/_tools/_DCC/MayaScope/AnalyseAdv/ADV_6.925_reference/AdvancedSkeleton.mel')
def main():
    from maya import cmds,mel
    output=ROOT/'validation/results/original-bendy-reference'
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',scope='Untouched original complete Body build with Shoulder/Elbow Bendy 3 and OPM')
    try:
        assert SOURCE.read_bytes()==REFERENCE.read_bytes()
        report['source_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        mel.eval('source "'+SOURCE.as_posix()+'";')
        cmds.optionVar(intValue=('asHaveRanThisVersion',1));cmds.optionVar(intValue=('asDock',0))
        mel.eval('AdvancedSkeleton;')
        cmds.file(str(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'),
                  open=True,force=True,executeScriptNodes=False)
        cmds.checkBox('asBodyOffsetParentMatrixCheckBox',edit=True,value=True)
        for joint in ('Shoulder','Elbow'):cmds.setAttr(joint+'.bendyCtrls',3)
        cmds.createNode('transform',name='asBatch')
        mel.eval('asBuildAdvancedSkeleton;')
        assert cmds.objExists('Root_M') and cmds.objExists('MicroXElbowPart1_L')
        body=cmds.listRelatives('Root_M',allDescendents=True,fullPath=True,type='joint') or []
        body+=cmds.ls('Root_M',long=True)
        neutral={node.rsplit('|',1)[-1]:cmds.xform(node,q=True,ws=True,m=True) for node in body}
        report['joint_count']=len(body)
        report['neutral_body']=neutral
        samples=[]
        for angle in (0.,30.,-45.):
            cmds.setAttr('FKElbow_R.rotateZ',angle)
            samples.append(dict(angle=angle,matrices={node:cmds.xform(node,q=True,ws=True,m=True)
                for node in ('Shoulder_R','ShoulderPart1_R','ShoulderPart2_R',
                             'Elbow_R','ElbowPart1_R','ElbowPart2_R','Wrist_R')}))
        cmds.setAttr('FKElbow_R.rotateZ',0.)
        report['elbow_samples']=samples
        saved=output/'original-bendy-reference.mb'
        cmds.file(rename=str(saved));cmds.file(save=True,type='mayaBinary',force=True)
        report['scene']=str(saved);report['status']='native_build_passed'
    except Exception:
        report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (output/'original-bendy-reference.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        cmds.quit(force=True)
