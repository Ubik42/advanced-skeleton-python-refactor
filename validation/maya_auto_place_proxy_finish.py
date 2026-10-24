"""Finish actual seven-axis native/Python proxy outputs, undo and reopen."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/auto-place-proxy-finish'
INPUT=ROOT/'validation/results/auto-place-proxy-full'


def snapshot():
    from maya import cmds as c
    from maya_original_fit_auto_place_sample import snapshot as fit_snapshot
    result=fit_snapshot()
    result.update(skin_visible=c.getAttr('ProxySkin.visibility'),
                  shoulder_guide=c.objExists('asFitShoulderStraight'),
                  finger_blend=c.objExists('straightenBS'))
    return result


def error(a,b):
    assert a['joints'].keys()==b['joints'].keys()
    for key in ('guides','skin_visible','shoulder_guide','finger_blend'):
        assert a[key]==b[key],(key,a[key],b[key])
    return max(abs(x-y) for name,row in a['joints'].items()
               for x,y in zip(row['matrix'],b['joints'][name]['matrix']))


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.application.fit_auto_place import FinishFitAutoPlace
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),scope='Full seven-axis connected proxy source/Python finish lifecycle; not original default-model acceptance')
    option_names=('asHaveRanThisVersion','asDock')
    options={name:c.optionVar(query=name) if c.optionVar(exists=name) else None for name in option_names}
    try:
        scan=json.loads((INPUT/'report.json').read_text())
        assert scan['status']=='passed' and scan['python']['result']['four'] and scan['python']['result']['guides']
        report['scan_pid']=scan['pid']
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.workspaceControl('asWorkspaceControl',label='ADV reference',dockToControl=('ToolBox','left'),retain=False)
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1));mel.eval('AdvancedSkeleton;')
        for mode in ('native','python'):
            c.file(str(INPUT/(mode+'-output.mb')),open=True,force=True,executeScriptNodes=False)
            for field,value in (('Skin','ProxySkin'),('All',''),('RightEye',''),('LeftEye','')):
                c.textField('asBody'+field+'TextField',edit=True,text=value)
            c.select('ProxySkin',replace=True)
            before=snapshot();assert before['guides']
            if mode=='native':mel.eval('asFitDeleteGuides;')
            else:
                result=FinishFitAutoPlace(MayaFitJointHost()).apply(skin=('ProxySkin',))
                report['python_result']=dict(finished=result.finished,fingers=result.restored_fingers,arm=result.restored_arm)
            after=snapshot();assert not after['guides'] and after['skin_visible']
            report[mode]=after
            if mode=='python':
                c.undo();undo=error(before,snapshot());assert undo<=1e-8,undo
                c.redo();redo=error(after,snapshot());assert redo<=1e-8,redo
                report['undo_error']=undo;report['redo_error']=redo
            scene=OUT/(mode+'-finished.mb')
            c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
            c.file(str(scene),open=True,force=True,executeScriptNodes=False)
            reopened=error(after,snapshot());assert reopened<=1e-8,reopened
            report[mode+'_reopen_error']=reopened
            (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        difference=error(report['native'],report['python']);assert difference<=1e-4,difference
        fat=max(abs(row['fat']-report['python']['joints'][name]['fat']) for name,row in report['native']['joints'].items() if row['fat'] is not None)
        assert fat<=1e-4,fat
        report.update(status='passed',maximum_joint_matrix_error=difference,maximum_fat_error=fat)
    except Exception:report.update(status='failed',error=traceback.format_exc())
    finally:
        if c.workspaceControl('asWorkspaceControl',exists=True):c.deleteUI('asWorkspaceControl',control=True)
        for name,value in options.items():
            if value is None:c.optionVar(remove=name)
            else:c.optionVar(intValue=(name,int(value)))
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred('quit -force')
    return 0 if report['status']=='passed' else 1
