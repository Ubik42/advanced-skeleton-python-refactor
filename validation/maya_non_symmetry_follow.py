"""Authored left/right Follow, spaces, named targets and constraints against MEL."""
from pathlib import Path
import json, os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-non-symmetry-follow-current'


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from maya_original_biped_current_smoke import main as build
    from maya_source_rp_sub_constructor import snapshot,difference
    OUT.mkdir(parents=True,exist_ok=True)
    previous=json.loads((OUT/'report.json').read_text()) if os.environ.get('ADV_NON_SYMMETRY_FOLLOW_POSES_ONLY')=='1' else None
    report=dict(status='running',pid=os.getpid(),scope='Authored asymmetric Fit follow, named follow, spaces, IK follow and parent constraint; full preserved rebuild; no attachment mesh or FBX.')
    from maya.api import OpenMaya as om
    messages=[]
    def capture_output(message,kind,*unused):
        messages.append((int(kind),message))
        if len(messages)>100:del messages[:-100]
    callback=om.MCommandMessage.addCommandOutputCallback(capture_output)
    options={name:c.optionVar(query=name) if c.optionVar(exists=name) else None
        for name in ('asHaveRanThisVersion','asDock')}
    def checkpoint(stage):
        report['stage']=stage
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        c.file(str(ROOT/'validation/results/source-non-symmetry-current/asymmetric-input.ma'),open=True,force=True,executeScriptNodes=False)
        rows=(('Scapula','follow','Root'),('Scapula_NonSymmetry','follow','Hip'),
              ('Wrist','ikFollow','Chest'),('Wrist_NonSymmetry','ikFollow','Root'),
              ('IndexFinger1','parentConstraint','Wrist'),('IndexFinger1_NonSymmetry','parentConstraint','Chest'),
              ('RingFinger1','followRoot',3.),('RingFinger1_NonSymmetry','followRoot',7.),
              ('PinkyFinger1','followSpaces',True),('PinkyFinger1_NonSymmetry','followSpaces',True))
        for node,attribute,value in rows:
            if not c.objExists(node+'.'+attribute):
                if isinstance(value,str):c.addAttr(node,longName=attribute,attributeType='enum',enumName=value,keyable=True)
                else:c.addAttr(node,longName=attribute,attributeType='bool' if isinstance(value,bool) else 'double')
            if isinstance(value,str):c.setAttr(node+'.'+attribute,0)
            else:c.setAttr(node+'.'+attribute,value)
        for node in ('Scapula','Scapula_NonSymmetry'):
            for attribute in ('followLeftRight','followWorld'):
                if not c.objExists(node+'.'+attribute):c.addAttr(node,longName=attribute,attributeType='bool',keyable=True)
        report['authored_fields']=rows
        input_scene=OUT/'input.ma'
        c.file(rename=str(input_scene));c.file(save=True,type='mayaAscii',force=True)
        checkpoint('original_build')
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1))
        c.workspaceControl('asWorkspaceControl',label='ADV reference',dockToControl=('ToolBox','left'),retain=False)
        mel.eval('AdvancedSkeleton;')
        for field in ('SubControllers','ExtraControllers','OffsetParentMatrix'):
            c.checkBox('asBody'+field+'CheckBox',edit=True,value=False)
        c.scriptEditorInfo(historyFilename=str(OUT/'native-history.log'),writeHistory=True,suppressErrors=False,suppressWarnings=False)
        native_scene=OUT/'native.mb'
        if os.environ.get('ADV_REUSE_NON_SYMMETRY_FOLLOW_REFERENCE')=='1':
            assert native_scene.is_file()
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            report['native_reference_pid']=56884
        else:
            c.createNode('transform',name='asBatch');mel.eval('asBuildAdvancedSkeleton;')
            c.file(rename=str(native_scene));c.file(save=True,type='mayaBinary',force=True)
        neutral=snapshot()
        poses=(('chest',(('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.),)),
               ('left_follow',(('FKScapula_L.follow','AdvPy_Scapula_LFK.follow',5.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
               ('right_follow',(('FKScapula_R.follow','AdvPy_Scapula_RFK.follow',5.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
               ('left_ik_follow',(('FKIKArm_L.FKIKBlend','FKIKArm_L.FKIKBlend',10.),('IKArm_L.ikFollow','AdvPy_ArmIK_L.ikFollow',5.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
               ('right_ik_follow',(('FKIKArm_R.FKIKBlend','FKIKArm_R.FKIKBlend',10.),('IKArm_R.ikFollow','AdvPy_ArmIK_R.ikFollow',5.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
               ('right_named',(('FKRingFinger1_R.followRoot','AdvPy_RingFinger1_RFK.followRoot',5.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
               ('left_named',(('FKRingFinger1_L.followRoot','AdvPy_RingFinger1_LFK.followRoot',2.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
               ('right_space',(('FKPinkyFinger1_R.followParent','AdvPy_PinkyFinger1_RFK.followParent',0.),('FKPinkyFinger1_R.followMain','AdvPy_PinkyFinger1_RFK.followMain',10.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
               ('left_space',(('FKPinkyFinger1_L.followParent','AdvPy_PinkyFinger1_LFK.followParent',0.),('FKPinkyFinger1_L.followRoot','AdvPy_PinkyFinger1_LFK.followRoot',10.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
               ('right_constraint',(('FKIndexFinger1_R.parentConstraint','AdvPy_IndexFinger1_RFK.parentConstraint',5.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
               ('left_constraint',(('FKIndexFinger1_L.parentConstraint','AdvPy_IndexFinger1_LFK.parentConstraint',0.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))))
        native={}
        for label,edits in poses:
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            for a,b,value in edits:c.setAttr(a,value)
            native[label]=snapshot()
            assert difference(neutral,native[label])>1e-3,label
        checkpoint('python_build_and_rebuild')
        if previous is not None:
            report['lifecycle']=previous['lifecycle'];assert report['lifecycle']['status']=='passed'
            report['lifecycle_pid']=previous.get('lifecycle_pid',previous['pid'])
        else:
            report['lifecycle']=build(input_scene,OUT/'python',rebuild=True,export=False,bendy=True,standalone=False)
        report['poses']=[]
        for scene in ('original-biped-current.mb','original-biped-rebuilt.mb'):
            c.file(str(OUT/'python'/scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
            actual=snapshot()
            report.setdefault('neutral_errors',{})[scene]=difference(neutral,actual)
            errors={name:max(abs(a-b) for a,b in zip(neutral[name],actual[name])) for name in neutral}
            report.setdefault('neutral_largest',{})[scene]=sorted(errors.items(),key=lambda row:row[1],reverse=True)[:12]
            report.setdefault('neutral_matrices',{})[scene]={'native':neutral,'python':actual}
            for label,edits in poses:
                c.file(str(OUT/'python'/scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
                for a,b,value in edits:c.setAttr(b,value)
                report['poses'].append(dict(scene=scene,case=label,maximum_error=difference(native[label],snapshot())))
        report['status']='passed' if max(report['neutral_errors'].values())<=1e-4 and all(row['maximum_error']<=1e-4 for row in report['poses']) else 'failed'
    except Exception:
        report.update(status='failed',traceback=traceback.format_exc(),joint_count=len(c.ls(type='joint') or []),root_exists=c.objExists('Root_M'),fit_exists=c.objExists('FitSkeleton'),script_location=mel.eval('asGetScriptLocation;'))
    finally:
        c.scriptEditorInfo(writeHistory=False)
        report['maya_messages']=messages
        om.MMessage.removeCallback(callback)
        if c.workspaceControl('asWorkspaceControl',exists=True):c.deleteUI('asWorkspaceControl',control=True)
        for name,value in options.items():
            if value is None:c.optionVar(remove=name)
            else:c.optionVar(intValue=(name,int(value)))
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
