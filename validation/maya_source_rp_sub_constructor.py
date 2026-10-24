"""Complete RP constructor/default and Sub-controller source comparison batch."""
from pathlib import Path
import json,os,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-rp-sub-constructor-current'


def snapshot():
    from maya import cmds as c
    nodes=(c.listRelatives('Root_M',allDescendents=True,type='joint',fullPath=True) or [])+c.ls('Root_M',long=True)
    return {node.rsplit('|',1)[-1]:c.xform(node,query=True,worldSpace=True,matrix=True) for node in nodes}


def difference(a,b):
    assert a.keys()==b.keys(),(a.keys()-b.keys(),b.keys()-a.keys())
    return max(abs(x-y) for name in a for x,y in zip(a[name],b[name]))


def main(*,standalone=False,quit_on_finish=True):
    from maya import cmds as c,mel
    from maya_original_biped_current_smoke import main as build
    from maya_original_body_pose_compare import main as compare
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),default={},sub={},
        scope='Fresh non-OPM multi-Spline/Bendy default and Sub-controller creation, preserved rebuild lifecycle and original MEL poses; original tolerance retained')
    reevaluate=os.environ.get('ADV_RP_REEVALUATED_POSES')=='1'
    if reevaluate:report['pose_context']='Same edits after frame 2 then 1 reevaluation; supplemental to unchanged direct-edit baseline.'
    options={name:c.optionVar(query=name) if c.optionVar(exists=name) else None for name in ('asHaveRanThisVersion','asDock')}
    source=ROOT/'validation/results/source-spline-multi.ma'
    try:
        if os.environ.get('ADV_REUSE_RP_DEFAULT')=='1':
            previous=json.loads((OUT/'report.json').read_text())
            report['default']=previous['default']
            assert report['default']['lifecycle']['status']=='passed'
            poses=report['default']['poses'];assert len(poses['rows'])==71
            report['default_evidence_pid']=previous.get('default_evidence_pid',previous['pid'])
            report['sub']['native_reference_pid']=previous.get('sub',{}).get('native_reference_pid',previous['pid'])
            sub_input=OUT/'sub-input.ma';native_scene=OUT/'native-sub.mb'
            assert sub_input.exists() and native_scene.exists()
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            native=snapshot();report['sub']['neutral_native']=native
        else:
            default=OUT/'default';default.mkdir(exist_ok=True)
            report['default']['lifecycle']=build(source,default,rebuild=True,export=False,opm=False,bendy=True,standalone=False)
            reference=ROOT/'validation/results/original-spline-multi-nonopm-reference'
            try:
                compare(reference/'original-spline-multi-nonopm-reference.mb',default/'original-biped-current.mb',
                        reference/'original-spline-multi-nonopm-reference.json',default/'poses.json',extended=True,
                        spline_systems=('Spine_M','SplineTail_R','SplineTail_L','SplineSolo_L'),standalone=False)
            except AssertionError as error:report['default']['parity_error']=str(error)
            poses=json.loads((default/'poses.json').read_text());report['default']['poses']={key:value for key,value in poses.items() if key!='matrices'}
            (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            c.file(str(source),open=True,force=True,executeScriptNodes=False)
            for name,value in (('subControllers',True),('extraControllers',False),('useOffsetParentMatrix',False)):
                if not c.objExists('FitSkeleton.'+name):c.addAttr('FitSkeleton',longName=name,attributeType='bool')
                c.setAttr('FitSkeleton.'+name,value)
            for joint in ('Shoulder','Elbow'):c.setAttr(joint+'.bendyCtrls',3)
            sub_input=OUT/'sub-input.ma';c.file(rename=str(sub_input));c.file(save=True,type='mayaAscii',force=True)
            mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
            c.workspaceControl('asWorkspaceControl',label='ADV reference',dockToControl=('ToolBox','left'),retain=False)
            c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1));mel.eval('AdvancedSkeleton;')
            for field,value in (('SubControllers',True),('ExtraControllers',False),('OffsetParentMatrix',False)):
                c.checkBox('asBody'+field+'CheckBox',edit=True,value=value)
            c.createNode('transform',name='asBatch');mel.eval('asBuildAdvancedSkeleton;')
            native=snapshot();report['sub']['neutral_native']=native
            native_scene=OUT/'native-sub.mb';c.file(rename=str(native_scene));c.file(save=True,type='mayaBinary',force=True)
        native_poses={}
        for limb,side,axis,amount in (('Arm','R','X',-.15),('Arm','L','X',.15),('Leg','R','Y',.15),('Leg','L','Y',.15)):
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            handle='IK'+limb+'Handle_'+side;parent=c.listRelatives(handle,parent=True)[0]
            if limb=='Arm':assert parent=='IKSub'+limb+'_'+side,(handle,parent)
            # Source Leg Handle is finally under RollToes; IKSub is upstream.
            parent='IKSub'+limb+'_'+side
            c.setAttr('FKIK'+limb+'_'+side+'.FKIKBlend',10.)
            before=snapshot();c.setAttr(parent+'.translate'+axis,amount);c.setAttr(parent+'.rotateY',15.)
            if reevaluate:c.currentTime(2);c.currentTime(1)
            after=snapshot();assert difference(before,after)>1e-3
            native_poses[limb+'_'+side]=after
        python=OUT/'sub';python.mkdir(exist_ok=True)
        if os.environ.get('ADV_REUSE_RP_SUB')=='1':
            assert previous['sub']['lifecycle']['status']=='passed'
            report['sub']['lifecycle']=previous['sub']['lifecycle']
            report['sub']['lifecycle_evidence_pid']=previous['sub'].get('lifecycle_evidence_pid',previous['pid'])
        else:
            report['sub']['lifecycle']=build(sub_input,python,rebuild=True,export=False,opm=False,bendy=True,standalone=False)
        c.file(str(python/'original-biped-current.mb'),open=True,force=True,executeScriptNodes=False)
        report['sub']['neutral_error']=difference(native,snapshot())
        report['sub']['sub_poses']=[]
        for limb,side,axis,amount in (('Arm','R','X',-.15),('Arm','L','X',.15),('Leg','R','Y',.15),('Leg','L','Y',.15)):
            c.file(str(python/'original-biped-current.mb'),open=True,force=True,executeScriptNodes=False)
            handle='AdvPy_'+limb+'IKHandle_'+side;parent=c.listRelatives(handle,parent=True)[0]
            if limb=='Arm':assert parent=='AdvPy_'+limb+'IKSub_'+side,(handle,parent)
            parent='AdvPy_'+limb+'IKSub_'+side
            c.setAttr('FKIK'+limb+'_'+side+'.FKIKBlend',10.)
            before=snapshot();c.setAttr(parent+'.translate'+axis,amount);c.setAttr(parent+'.rotateY',15.)
            if reevaluate:c.currentTime(2);c.currentTime(1)
            after=snapshot();assert difference(before,after)>1e-3
            error=difference(native_poses[limb+'_'+side],after)
            report['sub']['sub_poses'].append(dict(limb=limb,side=side,maximum_error=error,parent=parent))
        report['sub']['status']=('passed' if report['sub']['neutral_error']<=1e-4
            and all(row['maximum_error']<=1e-4 for row in report['sub']['sub_poses']) else 'failed')
        report['status']=('passed' if poses['status']=='passed'
            and report['sub']['status']=='passed' else 'failed')
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        if c.workspaceControl('asWorkspaceControl',exists=True):c.deleteUI('asWorkspaceControl',control=True)
        for name,value in options.items():
            if value is None:c.optionVar(remove=name)
            else:c.optionVar(intValue=(name,int(value)))
        report_path=OUT/('poses-time-reevaluation.json' if reevaluate else 'report.json')
        report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
