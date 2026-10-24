"""Complete biped with Spline parent Parts, native poses and preserved rebuild."""
from pathlib import Path
import json,os,sys,traceback,faulthandler
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-spline-part-lifecycle-current'

def main(standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from maya_original_biped_current_smoke import main as build
    from maya_source_rp_sub_constructor import snapshot,difference
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    OUT.mkdir(parents=True,exist_ok=True)
    trace=(OUT/'python-stack.log').open('w',encoding='utf-8')
    faulthandler.dump_traceback_later(45,file=trace,repeat=True)
    previous=json.loads((OUT/'report.json').read_text(encoding='utf-8')) if os.environ.get('ADV_SPLINE_PART_REUSE_LIFECYCLE')=='1' else None
    report=dict(status='running',pid=os.getpid(),configurations=[])
    def save(): (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        for opm in (False,True):
            prior=next((row for row in previous['configurations'] if row['opm']==opm and row.get('stage')=='complete' and row.get('lifecycle',{}).get('status')=='passed'),None) if previous else None
            if prior is not None:
                prior.setdefault('evidence_pid',previous.get('pid'));report['configurations'].append(prior);save();continue
            folder=OUT/('opm' if opm else 'traditional');folder.mkdir(exist_ok=True)
            input_scene=folder/'input.ma';native_scene=folder/'native.mb'
            reuse=os.environ.get('ADV_SPLINE_PART_REUSE_NATIVE')=='1' and input_scene.exists() and native_scene.exists()
            item=dict(opm=opm,stage='native-reference' if reuse else 'native-build',poses=[])
            report['configurations'].append(item);save()
            if reuse:
                mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
                c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
                item['reused_native_reference']=True
            else:
                c.file(str(ROOT/'validation/results/source-spline-multi.ma'),open=True,force=True,executeScriptNodes=False)
                if not c.objExists('FitSkeleton.useOffsetParentMatrix'):c.addAttr('FitSkeleton',longName='useOffsetParentMatrix',attributeType='bool')
                c.setAttr('FitSkeleton.useOffsetParentMatrix',opm)
                c.parent('Tail0','HeadEnd',absolute=True)
                if not c.objExists('HeadEnd.twistJoints'):c.addAttr('HeadEnd',longName='twistJoints',attributeType='long',defaultValue=2)
                c.setAttr('HeadEnd.twistJoints',2)
                if not c.objExists('Root.numMainExtras'):c.addAttr('Root',longName='numMainExtras',attributeType='long',defaultValue=2)
                c.setAttr('Root.numMainExtras',2)
                input_scene=folder/'input.ma';c.file(rename=str(input_scene));c.file(save=True,type='mayaAscii',force=True)
                mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
                c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1))
                if c.workspaceControl('asWorkspaceControl',exists=True):c.deleteUI('asWorkspaceControl')
                c.workspaceControl('asWorkspaceControl',label='ADV reference',dockToControl=('ToolBox','left'),retain=False)
                mel.eval('AdvancedSkeleton;')
                for field,value in (('SubControllers',False),('ExtraControllers',False),('OffsetParentMatrix',opm)):
                    c.checkBox('asBody'+field+'CheckBox',edit=True,value=value)
                c.createNode('transform',name='asBatch');mel.eval('asBuildAdvancedSkeleton;')
                native_scene=folder/'native.mb';c.file(rename=str(native_scene));c.file(save=True,type='mayaBinary',force=True)
            poses=[('neutral',())]
            for side in ('R','L'):
                for weight in (0.,5.,10.):
                    poses.append((side+str(weight),(
                        ('FKIKSplineTail_'+side+'.FKIKBlend','FKIKSplineTail_'+side+'.FKIKBlend',10.),
                        ('IKSplineTail3_'+side+'.followHeadEnd','AdvPy_Spline_SplineTail_'+side+'_IK2.followHeadEnd',weight),
                        ('FKHeadEnd_M.rotateZ','AdvPy_HeadEnd_MFK.rotateZ',12.),
                        ('Main.rotateY','AdvPy_Global.rotateY',17.))))
            native={}
            for label,edits in poses:
                c.file(str(native_scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
                for a,b,value in edits:c.setAttr(a,value)
                native[label]=snapshot()
            item['stage']='python-lifecycle';save()
            item['lifecycle']=build(input_scene,folder/'python',rebuild=True,export=False,bendy=False,opm=opm,standalone=False)
            for scene in ('original-biped-current.mb','original-biped-rebuilt.mb'):
                c.file(str(folder/'python'/scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
                registration=MayaBodyBuildHost().read_character_registration()
                layouts=tuple(p for p in (registration.spine,*registration.additional_spines) if p)
                tails=tuple(p for p in layouts if p.system_name.startswith('SplineTail_'))
                assert len(tails)==2
                for p in tails:
                    assert p.source_follow_parent==p.body_joints[0].rsplit('|',1)[0]
                    assert 'Part' in p.source_follow_parent
                    assert p.source_follow_targets[-1][0]=='HeadEnd'
                for label,edits in poses:
                    c.file(str(folder/'python'/scene),open=True,force=True,executeScriptNodes=False);c.currentTime(1)
                    for a,b,value in edits:c.setAttr(b,value)
                    item['poses'].append(dict(scene=scene,case=label,maximum_error=difference(native[label],snapshot())))
            item['maximum_error']=max(row['maximum_error'] for row in item['poses'])
            item['stage']='complete';save()
        report['maximum_error']=max(item['maximum_error'] for item in report['configurations'])
        report['status']='passed' if report['maximum_error']<=1e-4 else 'failed'
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        faulthandler.cancel_dump_traceback_later();trace.close()
        save()
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
