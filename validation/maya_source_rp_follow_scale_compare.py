"""Locate whole-character scale differences against the preserved prior graph."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-rp-follow-scale-current'


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.adapters.maya_source_rp_follow import decode,MARKER
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),configurations=[])
    native_names=('Main','RootX_M','Chest_M','IKOffsetArm_R','IKArm_R','PoleOffsetArm_R','PoleArm_R',
        'IKParentConstraintShoulder_R','IKXShoulder_R','IKXElbow_R','IKXWrist_R',
        'IKOffsetLeg_R','IKLeg_R','PoleOffsetLeg_R','PoleLeg_R','PoleAimLeg_R','PoleAim2Leg_R',
        'IKParentConstraintHip_R','IKXHip_R','IKXKnee_R','IKXAnkle_R')
    python_names=('AdvPy_Global','AdvPy_RootX_M','Chest_M','AdvPy_ArmIKOffset_R','AdvPy_ArmIK_R','AdvPy_ArmPVOffset_R','AdvPy_ArmPV_R',
        'AdvPy_ArmIKParent_R','AdvPy_ShoulderIKDriver_R','AdvPy_ElbowIKDriver_R','AdvPy_WristIKDriver_R',
        'AdvPy_LegIKOffset_R','AdvPy_LegIK_R','AdvPy_LegPVOffset_R','AdvPy_LegPV_R','AdvPy_LegFollow_RAim','AdvPy_LegFollow_RTarget',
        'AdvPy_LegIKParent_R','AdvPy_HipIKDriver_R','AdvPy_KneeIKDriver_R','AdvPy_AnkleIKDriver_R')
    def snapshot():
        nodes=(c.listRelatives('Root_M',allDescendents=True,type='joint',fullPath=True) or [])+c.ls('Root_M',long=True)
        return {n.rsplit('|',1)[-1]:c.xform(n,q=True,ws=True,matrix=True) for n in nodes}
    try:
        for mode in ('traditional','opm'):
            item=dict(name=mode,states={},comparisons=[]);report['configurations'].append(item)
            prior=ROOT/'validation/results/source-spline-part-lifecycle-current'/mode
            current=ROOT/'validation/results/source-rp-follow-lifecycle-current'/mode
            for label,scene in (('native',prior/'native.mb'),('old',prior/'python/original-biped-current.mb'),('current',current/'original-biped-current.mb')):
                item['states'][label]={}
                for pose in ('neutral','main_nonuniform','arm_ik_main_nonuniform','arm_stretch'):
                    c.file(str(scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
                    if pose in ('main_nonuniform','arm_ik_main_nonuniform'):
                        for axis,value in zip('XYZ',(1.2,.85,1.1)):c.setAttr(('Main' if label=='native' else 'AdvPy_Global')+'.scale'+axis,value)
                    if pose in ('arm_ik_main_nonuniform','arm_stretch'):c.setAttr('FKIKArm_R.FKIKBlend',10.)
                    if pose=='arm_stretch':
                        ctrl='IKArm_R' if label=='native' else 'AdvPy_ArmIK_R'
                        c.setAttr(ctrl+'.translateX',-2.);c.setAttr(ctrl+'.stretchy',10.)
                    c.dgdirty(allPlugs=True)
                    pairs=native_names if label=='native' else python_names
                    state=dict(body=snapshot(),controls={})
                    for role,node in zip(native_names,pairs):
                        if not c.objExists(node):state['controls'][role]=dict(missing=node);continue
                        state['controls'][role]=dict(matrix=c.xform(node,q=True,ws=True,matrix=True),
                            local=c.getAttr(node+'.matrix'),opm=c.getAttr(node+'.offsetParentMatrix'),
                            inherits=c.getAttr(node+'.inheritsTransform'),
                            scale=c.getAttr(node+'.scale'),rotation=c.getAttr(node+'.rotate'))
                    item['states'][label][pose]=state
                if label!='native':
                    reg=MayaBodyBuildHost().read_character_registration()
                    item[label+'_native_flags']=[s.source_rp for b in reg.source_limbs for s in decode(c.getAttr(b.ik_control+'.'+MARKER))[0].spaces]
            for pose in item['states']['native']:
                native=item['states']['native'][pose]
                for label in ('old','current'):
                    actual=item['states'][label][pose]
                    errors={n:max(abs(a-b) for a,b in zip(native['body'][n],actual['body'][n])) for n in native['body']}
                    controls={role:max(abs(a-b) for a,b in zip(row['matrix'],actual['controls'][role]['matrix']))
                        for role,row in native['controls'].items() if 'matrix' in row and 'matrix' in actual['controls'][role]}
                    item['comparisons'].append(dict(pose=pose,version=label,maximum_error=max(errors.values()),
                        largest=sorted(errors.items(),key=lambda row:row[1],reverse=True)[:8],control_errors=controls))
            (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        report['status']='passed' # Diagnostic collection completed; numerical errors are retained above.
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
