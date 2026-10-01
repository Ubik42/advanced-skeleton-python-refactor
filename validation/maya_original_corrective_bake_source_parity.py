"""Unmodified ADV Bake in Maya GUI against the Python Body fixture.

Run with maya.exe -script and a deferred entry, not standalone. Original MEL
needs its real UI. Fixture names and legacy pose text are translated before
execution; this compares corrective algorithms on the same Python Body, not
original Body construction or the full default-character appearance.
"""
from pathlib import Path
import json,sys,traceback,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUTPUT=ROOT/'validation/results/corrective-bake-original-gui'
SOURCE=ROOT/'local/adv_6_925/AdvancedSkeleton.mel'
REFERENCE=Path('D:/3D/_tools/_DCC/MayaScope/AnalyseAdv/ADV_6.925_reference/AdvancedSkeleton.mel')


def main():
    from maya import cmds,mel
    from adv_py.adapters.maya_corrective_shapes import MayaCorrectiveShapesHost
    from maya_original_corrective_bake_smoke import create_bake_fixture
    OUTPUT.mkdir(parents=True,exist_ok=True)
    report={'status':'running','stages':[]}
    try:
        assert SOURCE.read_bytes()==REFERENCE.read_bytes(),'Local package MEL differs from reference'
        report['source_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        cmds.file(str(ROOT/'validation/results/biped-primary-controls-final/original-biped-current.mb'),open=True,force=True,executeScriptNodes=False)
        host=MayaCorrectiveShapesHost()
        control=create_bake_fixture(cmds,host)
        # Translate only fixture identity and neutral-pose serialization. All
        # original procedures below execute unchanged with their actual UI.
        neutral=tuple(('AdvPy_Wrist_RFK.'+kind+axis,cmds.getAttr('AdvPy_Wrist_RFK.'+kind+axis)) for kind in ('translate','rotate','scale') for axis in 'XYZ')
        control=cmds.rename(control,'FKWrist_R')
        commands=''.join('setAttr '+plug.replace('AdvPy_Wrist_RFK.','FKWrist_R.')+' '+str(value)+';' for plug,value in neutral)
        if not cmds.objExists('buildPose.udAttr'):cmds.addAttr('buildPose',ln='udAttr',dt='string')
        cmds.setAttr('buildPose.udAttr',commands,type='string')
        report['fixture_pose_scope']='Selected Wrist primary TRS; other Body limbs prepared neutral/all-FK before native execution'
        mel.eval('source "'+SOURCE.as_posix()+'";')
        cmds.optionVar(intValue=('asHaveRanThisVersion',1))
        cmds.optionVar(intValue=('asDock',0))
        mel.eval('AdvancedSkeleton;')
        report['stages'].append('original_ui_loaded')
        for name,value in [('asCorrectiveShapesQRotateCheckBox',True),('asCorrectiveShapesUseSoftModsCheckBox',False),('asCorrectiveShapesMirrorCheckBox',False)]:
            cmds.checkBox(name,e=True,v=value)
        cmds.textField('asBakeToCorrective1TextField',e=True,text='BakeSource')
        cmds.textField('asBakeToCorrective2TextField',e=True,text='BakeDestination')
        for axis in 'XYZ':
            for sign in (1,2):cmds.checkBox('asBake'+axis+str(sign)+'CheckBox',e=True,v=True)
        cmds.select(control,r=True)
        mel.eval('asBakeIntoCorrectiveShapes;')
        report['stages'].append('unmodified_original_six_axis_bake')
        aliases=cmds.aliasAttr('BakeDestinationCorrective',q=True) or []
        report['target_aliases']=aliases[::2]
        report['samples']=[]
        def points(node):
            cmds.dgdirty(allPlugs=True)
            return cmds.xform(node+'.vtx[*]',q=True,ws=True,t=True)
        for axis in 'xyz':
            for amount in (90,-90):
                cmds.setAttr(control+'.rotate',0,0,0,type='double3')
                cmds.setAttr(control+'.r'+axis,amount)
                source=points('BakeSource');target=points('BakeDestination')
                report['samples'].append({'axis':axis,'amount':amount,'maximum_geometry_error':max(abs(a-b) for a,b in zip(source,target)),'source_first_vertex':source[:3],'destination_first_vertex':target[:3],'qrotation':[cmds.getAttr('Wrist_R.qRotate'+a) for a in 'XYZ'],'source_vertices':source,'destination_vertices':target})
        report['status']='original_bake_measured'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc()
    finally:
        (OUTPUT/'source-bake.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        try:
            cmds.file(rename=str(OUTPUT/'source-bake.mb'));cmds.file(save=True,type='mayaBinary',force=True)
        finally:cmds.quit(force=True)
