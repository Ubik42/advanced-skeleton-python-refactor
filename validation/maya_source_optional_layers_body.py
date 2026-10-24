"""Full Sub+Extra source/Python Body, layer animation and preserved rebuild."""
from pathlib import Path
import json, os, sys, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/source-optional-layers-body-current'


def edits():
    rows=[]
    for limb in ('Arm','Leg'):
        for side in ('R','L'):
            mode=('FKIK'+limb+'_'+side+'.FKIKBlend',
                  'FKIK'+limb+'_'+side+'.FKIKBlend',10.,10.)
            for layer in ('Sub','Extra'):
                rows.append((limb+'_'+side+'_'+layer,(mode,
                    ('IK'+layer+limb+'_'+side+'.translateZ',
                     'AdvPy_'+limb+'IK'+layer+'_'+side+'.translateZ',.15,.15),
                    ('IK'+layer+limb+'_'+side+'.rotateY',
                     'AdvPy_'+limb+'IK'+layer+'_'+side+'.rotateY',15.,15.))))
    for side in ('R','L'):
        for layer in ('Sub','Extra'):
            rows.append(('FKShoulder_'+side+'_'+layer,(
                ('FK'+layer+'Shoulder_'+side+'.rotateY',
                 'AdvPy_Shoulder_'+side+'FK'+layer+'.rotateY',20.,20.),)))
    return rows


def main(*,standalone=False,quit_on_finish=True):
    if os.environ.get('ADV_OPTIONAL_POSES_ONLY')=='1':
        return compare_saved(quit_on_finish=quit_on_finish)
    from maya import cmds as c,mel
    from maya_original_biped_current_smoke import main as build
    from maya_source_rp_sub_constructor import snapshot,difference
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',pid=os.getpid(),scope=
        'Fresh complete non-OPM multi-Spline/Bendy Body with Sub and Extra enabled; '
        '12 optional-layer original poses and native Sub/Extra animation retained '
        'through Skin, save/reopen, rebuild and Undo/Redo. Proxy mesh, no FBX.')
    options={name:c.optionVar(query=name) if c.optionVar(exists=name) else None
             for name in ('asHaveRanThisVersion','asDock')}
    def checkpoint(stage):
        report['stage']=stage
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        checkpoint('native_build')
        source=OUT/'input.ma';native_scene=OUT/'native.mb'
        c.file(str(ROOT/'validation/results/source-rp-sub-constructor-current/sub-input.ma'),
               open=True,force=True,executeScriptNodes=False)
        c.setAttr('FitSkeleton.extraControllers',True)
        c.file(rename=str(source));c.file(save=True,type='mayaAscii',force=True)
        mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
        c.workspaceControl('asWorkspaceControl',label='ADV reference',dockToControl=('ToolBox','left'),retain=False)
        c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',1));mel.eval('AdvancedSkeleton;')
        for field,value in (('SubControllers',True),('ExtraControllers',True),('OffsetParentMatrix',False)):
            c.checkBox('asBody'+field+'CheckBox',edit=True,value=value)
        c.createNode('transform',name='asBatch');mel.eval('asBuildAdvancedSkeleton;')
        native=snapshot();c.file(rename=str(native_scene));c.file(save=True,type='mayaBinary',force=True)
        checkpoint('native_optional_layer_poses')
        poses={}
        for label,changes in edits():
            c.file(str(native_scene),open=True,force=True,executeScriptNodes=False)
            before=snapshot()
            for a,b,x,y in changes:c.setAttr(a,x)
            poses[label]=snapshot();assert difference(before,poses[label])>1e-3,label
        report['native_poses']=len(poses)
        animated=tuple(('AdvPy_'+limb+'IK'+layer+'_'+side,'rotateY',10.)
                       for limb in ('Arm','Leg') for layer in ('Sub','Extra') for side in ('R','L'))
        python=OUT/'python'
        checkpoint('python_build_skin_animation_rebuild')
        report['lifecycle']=build(source,python,rebuild=True,export=False,opm=False,
            bendy=True,standalone=False,additional_animation=animated)
        checkpoint('python_optional_layer_poses')
        c.file(str(python/'original-biped-current.mb'),open=True,force=True,executeScriptNodes=False)
        c.currentTime(1)
        report['neutral_error']=difference(native,snapshot())
        report['poses']=[]
        for label,changes in edits():
            c.file(str(python/'original-biped-current.mb'),open=True,force=True,executeScriptNodes=False)
            c.currentTime(1)
            # Animated layer channels are set at the same comparison frame.
            for a,b,x,y in changes:
                if c.listConnections(b,source=True,destination=False,type='animCurve'):
                    c.setKeyframe(b,time=1,value=y)
                else:c.setAttr(b,y)
            c.currentTime(2);c.currentTime(1)
            c.dgdirty(allPlugs=True)
            for a,b,x,y in changes:assert abs(c.getAttr(b)-y)<1e-8,(b,c.getAttr(b),y)
            error=difference(poses[label],snapshot())
            report['poses'].append(dict(case=label,maximum_error=error))
        report['status']=('passed' if report['neutral_error']<=1e-4
            and all(row['maximum_error']<=1e-4 for row in report['poses']) else 'failed')
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        if c.workspaceControl('asWorkspaceControl',exists=True):c.deleteUI('asWorkspaceControl',control=True)
        for name,value in options.items():
            if value is None:c.optionVar(remove=name)
            else:c.optionVar(intValue=(name,int(value)))
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1


def compare_saved(*,quit_on_finish=True):
    """Only pose readback after a completed lifecycle; never rebuild again."""
    from maya import cmds as c
    from maya_source_rp_sub_constructor import snapshot,difference
    previous=json.loads((OUT/'report.json').read_text())
    assert previous['lifecycle']['status']=='passed'
    report=dict(status='running',pid=os.getpid(),scope=previous['scope'],
        lifecycle=previous['lifecycle'],
        lifecycle_evidence_pid=previous.get('lifecycle_evidence_pid',previous['pid']),
        native_reference_pid=previous.get('native_reference_pid',previous['pid']))
    scenes=(OUT/'native.mb',OUT/'python/original-biped-current.mb')
    try:
        neutral=[];matrices={};inputs=[]
        for index,scene in enumerate(scenes):
            c.file(str(scene),open=True,force=True,executeScriptNodes=False)
            c.currentTime(1);neutral.append(snapshot())
            matrices[index]={}
            for label,changes in edits():
                c.file(str(scene),open=True,force=True,executeScriptNodes=False)
                c.currentTime(1)
                stale=[]
                for a,b,x,y in changes:
                    plug,value=(a,x) if index==0 else (b,y)
                    if c.listConnections(plug,source=True,destination=False,type='animCurve'):
                        c.setKeyframe(plug,time=1,value=value)
                        stale.append((plug,c.getAttr(plug),value))
                    else:c.setAttr(plug,value)
                # Maya's setKeyframe(value=...) sets a curve key without
                # necessarily updating the evaluated attribute at this time.
                c.currentTime(2);c.currentTime(1)
                c.dgdirty(allPlugs=True)
                for a,b,x,y in changes:
                    plug,value=(a,x) if index==0 else (b,y)
                    assert abs(c.getAttr(plug)-value)<1e-8,(plug,c.getAttr(plug),value)
                if stale:inputs.append(dict(case=label,before_time_reevaluation=stale,
                    actual_after=[c.getAttr(row[0]) for row in stale]))
                matrices[index][label]=snapshot()
        report['neutral_error']=difference(*neutral)
        report['poses']=[]
        for label,changes in edits():
            a,b=matrices[0][label],matrices[1][label]
            errors={node:max(abs(x-y) for x,y in zip(a[node],b[node])) for node in a}
            report['poses'].append(dict(case=label,maximum_error=max(errors.values()),
                largest=sorted(errors.items(),key=lambda item:item[1],reverse=True)[:5]))
        report['animation_input_checks']=inputs
        report['status']=('passed' if report['neutral_error']<=1e-4
            and all(row['maximum_error']<=1e-4 for row in report['poses']) else 'failed')
    except Exception:report.update(status='failed',traceback=traceback.format_exc())
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        completion=os.environ.get('ADV_TEST_COMPLETION_FILE')
        if completion and quit_on_finish:Path(completion).write_text(json.dumps(dict(pid=os.getpid(),status=report['status'])),encoding='utf-8')
        if quit_on_finish:c.evalDeferred(lambda:c.quit(force=True))
    return 0 if report['status']=='passed' else 1
