"""Authored left/right Follow, spaces, named targets and constraints against MEL."""
from pathlib import Path
import json, os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-non-symmetry-aim-current'


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from maya_original_biped_current_smoke import main as build
    from maya_source_rp_sub_constructor import snapshot,difference
    OUT.mkdir(parents=True,exist_ok=True)
    previous=json.loads((OUT/'report.json').read_text()) if os.environ.get('ADV_NON_SYMMETRY_AIM_POSES_ONLY')=='1' else None
    report=dict(status='running',pid=os.getpid(),scope='Authored asymmetric Fit AimAt, self/target Up Object and 0/5/10 weights; full preserved rebuild; no attachment mesh or FBX.')
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
        rows=(('MiddleFinger1','aimAt','IndexFinger1'),
              ('MiddleFinger1_NonSymmetry','aimAt','RingFinger1'))
        for node,attribute,value in rows:
            if not c.objExists(node+'.'+attribute):
                if isinstance(value,str):c.addAttr(node,longName=attribute,attributeType='enum',enumName=value,keyable=True)
                else:c.addAttr(node,longName=attribute,attributeType='bool' if isinstance(value,bool) else 'double')
            if isinstance(value,str):c.setAttr(node+'.'+attribute,0)
            else:c.setAttr(node+'.'+attribute,value)
        for node in ('MiddleFinger1','MiddleFinger1_NonSymmetry'):
            for attr, labels in (('aimAxis','x:y:z'),('aimUpAxis','x:y:z'),('aimUpObject','self:target')):
                if not c.objExists(node+'.'+attr):c.addAttr(node,longName=attr,attributeType='enum',enumName=labels,keyable=True)
            c.setAttr(node+'.aimAxis',0);c.setAttr(node+'.aimUpAxis',1)
            c.setAttr(node+'.aimUpObject',0 if node=='MiddleFinger1' else 1)
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
        if os.environ.get('ADV_REUSE_NON_SYMMETRY_AIM_REFERENCE')=='1':
            assert native_scene.is_file()
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            report['native_reference_pid']=55020
        else:
            c.createNode('transform',name='asBatch');mel.eval('asBuildAdvancedSkeleton;')
            c.file(rename=str(native_scene));c.file(save=True,type='mayaBinary',force=True)
        neutral=snapshot()
        poses=(
            ('right_target',(('FKIndexFinger1_R.rotateZ','AdvPy_IndexFinger1_RFK.rotateZ',20.),)),
            ('left_target',(('FKRingFinger1_R.rotateZ','AdvPy_RingFinger1_RFK.rotateZ',20.),)),
            ('right_half',(('FKMiddleFinger1_R.aimAt','AdvPy_MiddleFinger1_RFK.aimAt',5.),('FKIndexFinger1_R.rotateZ','AdvPy_IndexFinger1_RFK.rotateZ',20.))),
            ('left_half',(('FKMiddleFinger1_L.aimAt','AdvPy_MiddleFinger1_LFK.aimAt',5.),('FKRingFinger1_R.rotateZ','AdvPy_RingFinger1_RFK.rotateZ',20.))),
            ('right_zero',(('FKMiddleFinger1_R.aimAt','AdvPy_MiddleFinger1_RFK.aimAt',0.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))),
            ('left_zero',(('FKMiddleFinger1_L.aimAt','AdvPy_MiddleFinger1_LFK.aimAt',0.),('FKChest_M.rotateZ','AdvPy_Chest_MFK.rotateZ',10.))))
        poses += (
            ('left_target_position',(('FKWrist_R.rotateZ','AdvPy_Wrist_RFK.rotateZ',25.),)),
            ('left_target_position_half',(('FKMiddleFinger1_L.aimAt','AdvPy_MiddleFinger1_LFK.aimAt',5.),('FKWrist_R.rotateZ','AdvPy_Wrist_RFK.rotateZ',25.))),
            ('left_target_position_zero',(('FKMiddleFinger1_L.aimAt','AdvPy_MiddleFinger1_LFK.aimAt',0.),('FKWrist_R.rotateZ','AdvPy_Wrist_RFK.rotateZ',25.))))
        native={}
        for label,edits in poses:
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            for a,b,value in edits:c.setAttr(a,value)
            native[label]=snapshot()
            assert difference(neutral,native[label])>1e-3,label
        report['aim_weight_response'] = {
            'half_to_zero': difference(native['left_target_position_half'], native['left_target_position_zero']),
            'full_to_half': difference(native['left_target_position'], native['left_target_position_half'])}
        assert min(report['aim_weight_response'].values()) > 1e-3, report['aim_weight_response']
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
