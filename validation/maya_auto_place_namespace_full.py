"""Full public AutoPlace/finish lifecycle in a second character namespace."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/auto-place-namespace-full'
NS='OtherRig'


def snapshot(namespace=NS):
    from maya import cmds as c
    prefix=namespace+':' if namespace else ''
    return dict(guides=c.objExists(prefix+'AutoPlacing'),skin_visible=c.getAttr(prefix+'ProxySkin.visibility'),
        joints={name.replace(prefix,''):dict(matrix=c.xform(name,query=True,worldSpace=True,matrix=True),fat=c.getAttr(name+'.fat'))
                for name in c.listRelatives(prefix+'FitSkeleton',allDescendents=True,type='joint',fullPath=True)})


def native_scan_undo():
    from maya import cmds as c,mel
    from PySide2 import QtWidgets
    mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
    c.workspaceControl('asWorkspaceControl',label='ADV reference',dockToControl=('ToolBox','left'),retain=False)
    options={name:c.optionVar(query=name) if c.optionVar(exists=name) else None for name in ('asHaveRanThisVersion','asDock')}
    try:
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1));mel.eval('AdvancedSkeleton;')
        c.file(str(ROOT/'validation/results/auto-place-proxy-full/input.mb'),open=True,force=True,executeScriptNodes=False)
        QtWidgets.QApplication.processEvents()
        for field,value in (('Skin','ProxySkin'),('All',''),('RightEye',''),('LeftEye','')):
            c.textField('asBody'+field+'TextField',edit=True,text=value)
        before=snapshot('')
        c.undoInfo(openChunk=True,chunkName='Native complete AutoPlace scan')
        try:
            mel.eval('asFitAutoPlace;');QtWidgets.QApplication.processEvents()
        finally:c.undoInfo(closeChunk=True)
        placed=snapshot('');assert placed['guides']
        undo_name=c.undoInfo(query=True,undoName=True)
        c.undo();undone=snapshot('');undo=difference(before,undone)
        c.redo();redone=snapshot('');redo=difference(placed,redone)
        return dict(undo_name=undo_name,undo_error=undo,redo_error=redo,before=before,undone=undone,placed=placed,redone=redone)
    finally:
        if c.workspaceControl('asWorkspaceControl',exists=True):c.deleteUI('asWorkspaceControl',control=True)
        for name,value in options.items():
            if value is None:c.optionVar(remove=name)
            else:c.optionVar(intValue=(name,int(value)))


def difference(a,b):
    assert a['joints'].keys()==b['joints'].keys()
    assert a['guides']==b['guides']
    return max(abs(x-y) for name,row in a['joints'].items()
               for x,y in zip(row['matrix'],b['joints'][name]['matrix']))


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.application.fit_auto_place import AutoPlaceFit,FinishFitAutoPlace
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),scope='Full connected proxy AutoPlace/finish in OtherRig namespace, compared with accepted root native output; original default model not accepted')
    try:
        scan=json.loads((ROOT/'validation/results/auto-place-proxy-full/report.json').read_text())
        finish=json.loads((ROOT/'validation/results/auto-place-proxy-finish/report.json').read_text())
        assert scan['status']==finish['status']=='passed'
        if os.environ.get('ADV_REUSE_UNDO_REFERENCE')=='1':
            previous=json.loads((OUT/'report.json').read_text())
            assert previous['scan']['undo_native_error']==previous['scan']['redo_native_error']==0
            report['native_scan_undo']=previous['native_scan_undo']
            report['undo_reference_pid']=previous.get('undo_reference_pid',previous['pid'])
        else:report['native_scan_undo']=native_scan_undo()
        c.file(str(ROOT/'validation/results/auto-place-proxy-full/input.mb'),open=True,force=True,executeScriptNodes=False)
        # Import the complete original Fit asset into the namespace, including
        # its attached legacy DrivingSystem animCurves. Renaming only the DAG
        # leaves those real dependencies in the root character namespace.
        geometry=OUT/'geometry.mb'
        c.select('ProxySkin',replace=True)
        c.file(str(geometry),exportSelected=True,type='mayaBinary',force=True)
        c.file(new=True,force=True)
        c.file(str(ROOT/'local/adv_6_925/AdvancedSkeletonFiles/fitSkeletons/biped.ma'),
               i=True,namespace=NS,executeScriptNodes=False)
        c.file(str(geometry),i=True,namespace=NS,mergeNamespacesOnClash=True,executeScriptNodes=False)
        if not c.objExists(NS+':FitSkeleton.fitSkeletonTemplate'):
            c.addAttr(NS+':FitSkeleton',longName='fitSkeletonTemplate',dataType='string')
        c.setAttr(NS+':FitSkeleton.fitSkeletonTemplate','biped',type='string')
        c.select(clear=True);before=snapshot()
        host=MayaFitJointHost(namespace=NS);host._fit_auto_place_interactive=False
        result=AutoPlaceFit(host).apply(skin=(NS+':ProxySkin',))
        assert result.finger_detected and result.guides_active
        assert len(result.axes_completed)==7,result.axes_completed
        placed=snapshot();matrix=difference(scan['native']['output'],placed)
        assert matrix<=1e-4,matrix
        fat=max(abs(row['fat']-placed['joints'][name]['fat']) for name,row in scan['native']['output']['joints'].items())
        assert fat<=1e-4,fat
        # Preserve the normal successful result before exercising the inherited
        # stock scan Undo/Redo cache behavior. Normal reopen/finish validation
        # must use this scene, not the known altered native redo output.
        scene=OUT/'guides.mb';c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
        report['scan']=dict(axes=result.axes_completed,maximum_joint_matrix_error=matrix,maximum_fat_error=fat)
        c.undo();undone=snapshot();undo=difference(before,undone)
        report['scan']['undo_error']=undo
        report['scan']['before_native_error']=difference(report['native_scan_undo']['before'],before)
        report['scan']['undo_native_error']=difference(report['native_scan_undo']['undone'],undone)
        assert report['scan']['before_native_error']<=1e-8,report['scan']
        assert report['scan']['undo_native_error']<=1e-8,report['scan']
        c.redo();redone=snapshot();redo=difference(placed,redone)
        report['scan']['redo_error']=redo
        report['scan']['redo_native_error']=difference(report['native_scan_undo']['redone'],redone)
        assert report['scan']['redo_native_error']<=1e-8,report['scan']
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        reopened=difference(placed,snapshot());assert reopened<=1e-8,reopened
        report['guide_reopen_error']=reopened
        result=FinishFitAutoPlace(MayaFitJointHost(namespace=NS)).apply(skin=(NS+':ProxySkin',))
        after=snapshot();assert result.finished and not after['guides'] and after['skin_visible']
        matrix=difference(finish['native'],after);assert matrix<=1e-4,matrix
        c.undo();undo=difference(placed,snapshot());assert undo<=1e-8,undo
        c.redo();redo=difference(after,snapshot());assert redo<=1e-8,redo
        scene=OUT/'finished.mb';c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(scene),open=True,force=True,executeScriptNodes=False)
        reopened=difference(after,snapshot());assert reopened<=1e-8,reopened
        report['finish']=dict(maximum_joint_matrix_error=matrix,undo_error=undo,redo_error=redo,reopen_error=reopened,fingers=result.restored_fingers,arm=result.restored_arm)
        report['status']='passed'
    except Exception:report.update(status='failed',error=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred('quit -force')
    return 0 if report['status']=='passed' else 1
