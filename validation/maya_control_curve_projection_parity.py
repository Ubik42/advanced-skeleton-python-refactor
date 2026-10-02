"""Unedited ADV asProjectControlCurve compared with the Python public action."""
from pathlib import Path
import json
import math
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def fixture(name,kind='open',transformed=False):
    from maya import cmds as c
    c.file(new=True,force=True)
    c.polySphere(name='Skin',radius=3.,subdivisionsAxis=24,subdivisionsHeight=16)
    if kind=='periodic':
        control=c.circle(name=name,normal=(0,1,0),radius=1.,sections=8,constructionHistory=False)[0]
    else:
        points=[(math.cos(i*math.pi/18),.25*math.sin(i*math.pi/9),math.sin(i*math.pi/18))
                for i in range(37)]
        points[0]=(0.,0.,0.)
        control=c.curve(name=name,degree=1,point=points)
    if transformed:
        parent=c.createNode('transform',name='ControllerParent')
        c.parent(control,parent)
        c.setAttr(parent+'.rotate',11.,23.,-9.,type='double3')
        c.setAttr(parent+'.scale',1.3,.8,1.1,type='double3')
        c.setAttr(control+'.rotate',-4.,17.,2.,type='double3')
    c.select(control,replace=True)
    return control


def snapshot(control):
    from maya import cmds as c
    return {'points':c.xform(control+'.cv[*]',query=True,objectSpace=True,translation=True),
            'matrix':c.xform(control,query=True,worldSpace=True,matrix=True),
            'selection':c.ls(selection=True,long=True) or [],
            'uuids':set(c.ls(uuid=True) or [])}


def maximum(left,right):
    assert len(left)==len(right),(len(left),len(right))
    return max((abs(a-b) for a,b in zip(left,right)),default=0.)


def main(output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c,mel
    from adv_py.adapters.maya_body import MayaBodyBuildHost
    from adv_py.application.control_curves import AutoScaleControlCurves
    output.mkdir(parents=True,exist_ok=True)
    source=ROOT/'local/adv_6_925/AdvancedSkeleton.mel'
    mel.eval('source "'+source.as_posix()+'";')
    report={'status':'running','cases':[]}
    for name,kind,transformed in (('FKWrist_R','open',False),('FKElbow_R','periodic',False),
        ('FKShoulder_R','open',False),('FKHip_R','open',False),('FKCup_R','open',False),
        ('FKThumbFinger1_R','open',False),('FKThumbFinger2_R','open',False),
        ('FKChest_M','open',False),('RootX_M','open',False),('FKEye_R','open',False),
        ('FKJaw_M','open',False),('FKWrist_R','periodic',True)):
        row={'case':name+'_'+kind+('_transformed' if transformed else '')};report['cases'].append(row)
        try:
            control=fixture(name,kind,transformed)
            scene=output/(row['case']+'.mb')
            c.file(rename=str(scene));c.file(save=True,type='mayaBinary',force=True)
            initial=snapshot(control)
            mel.eval('asProjectControlCurve "'+control+'" "Skin";')
            native=snapshot(control)
            c.file(str(scene),open=True,force=True,executeScriptNodes=False)
            c.select(control,replace=True)
            baseline=snapshot(control)
            result=AutoScaleControlCurves(MayaBodyBuildHost()).apply((control,),'Skin')
            python=snapshot(control)
            error=maximum(native['points'],python['points'])
            assert error<=1e-5,error
            assert maximum(initial['matrix'],python['matrix'])<=1e-8
            assert initial['selection']==python['selection']
            assert baseline['uuids']==python['uuids'],'temporary nodes leaked'
            after=python['points']
            c.undo();assert maximum(baseline['points'],snapshot(control)['points'])<=1e-8
            c.redo();assert maximum(after,snapshot(control)['points'])<=1e-8
            persisted=output/(row['case']+'-python.mb')
            c.file(rename=str(persisted));c.file(save=True,type='mayaBinary',force=True)
            c.file(str(persisted),open=True,force=True,executeScriptNodes=False)
            assert maximum(after,snapshot(control)['points'])<=1e-8
            row.update(status='passed',maximum_error=error,projected_points=result.projected_points,
                       undo_redo=True,no_temporary_nodes=True)
            # FBX uses aliases and a separate host path; verify its actual
            # projection outputs, not just the protection-factor function.
            c.file(str(scene),open=True,force=True,executeScriptNodes=False)
            from adv_py.adapters.maya_fbx_rig_autoscale import _project_curve
            shape=c.listRelatives(control,shapes=True,type='nurbsCurve')[0]
            changed=_project_curve(c,control,shape,'Skin',source_control_name=name)
            fbx_error=maximum(native['points'],snapshot(control)['points'])
            assert fbx_error<=1e-5,fbx_error
            row.update(fbx_projection_error=fbx_error,fbx_projected_points=changed)
        except Exception:row.update(status='failed',error=traceback.format_exc())
        (output/'projection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    row={'case':'projection_failure_rollback'};report['cases'].append(row)
    try:
        control=fixture('FKWrist_R')
        baseline=snapshot(control)
        raw=c.polyProjectCurve
        calls=[0]
        def interrupted(*args,**kwargs):
            calls[0]+=1
            if calls[0]==4:raise RuntimeError('Injected failure after three projected points')
            return raw(*args,**kwargs)
        c.polyProjectCurve=interrupted
        try:
            AutoScaleControlCurves(MayaBodyBuildHost()).apply((control,),'Skin')
            raise AssertionError('Expected injected projection failure')
        except RuntimeError as exc:
            assert 'Injected failure' in str(exc),str(exc)
        finally:c.polyProjectCurve=raw
        restored=snapshot(control)
        assert maximum(baseline['points'],restored['points'])==0.
        assert baseline['uuids']==restored['uuids']
        assert baseline['selection']==restored['selection']
        row.update(status='passed',points_restored=True,scene_nodes_restored=True)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    row={'case':'namespace_and_foreign_temporary_names'};report['cases'].append(row)
    try:
        control=fixture('FKWrist_R','periodic',True)
        AutoScaleControlCurves(MayaBodyBuildHost()).apply((control,),'Skin')
        expected=snapshot(control)['points']
        control=fixture('FKWrist_R','periodic',True)
        c.namespace(add='ProjectionRig')
        parent=c.listRelatives(control,parent=True)[0]
        c.rename(parent,'ProjectionRig:'+parent)
        c.rename(control,'ProjectionRig:'+control)
        for shape in c.listRelatives('ProjectionRig:'+control,shapes=True):
            c.rename(shape,'ProjectionRig:'+shape)
        strangers={}
        for name in ('AdvPy_ControlProjectionTemp','asProjectTransform1','asProjectTransform2',
                     'asProjectTransform3','asProjectCurve','asProjectCurves'):
            node=c.createNode('transform',name=name)
            strangers[node]=c.ls(node,uuid=True)[0]
        c.select('ProjectionRig:'+control,replace=True)
        baseline=set(c.ls(uuid=True) or [])
        result=AutoScaleControlCurves(MayaBodyBuildHost(namespace='ProjectionRig')).apply(
            (control,),':Skin')
        assert maximum(expected,snapshot('ProjectionRig:'+control)['points'])<=1e-8
        assert baseline==set(c.ls(uuid=True) or [])
        assert all(c.ls(node,uuid=True)==[uuid] for node,uuid in strangers.items())
        row.update(status='passed',projected_points=result.projected_points,foreign_nodes_preserved=True)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    row={'case':'public_selection_and_empty_selection'};report['cases'].append(row)
    try:
        from adv_py.product.maya_panel_controller import MayaPanelController
        control=fixture('FKWrist_R','periodic')
        panel=MayaPanelController(host_factory=MayaBodyBuildHost)
        before=snapshot(control)
        assert panel.control_curves_auto_scale(':',(),'Skin')==1
        assert maximum(before['points'],snapshot(control)['points'])>1.
        c.select(clear=True)
        baseline=snapshot(control)
        assert panel.control_curves_auto_scale(':',(),'Skin')==0
        assert baseline==snapshot(control)
        row.update(status='passed',uses_current_selection=True,empty_selection_unchanged=True)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    row={'case':'no_projection_hit'};report['cases'].append(row)
    try:
        control=fixture('FKWrist_R','periodic')
        c.setAttr('Skin.translate',30.,30.,30.,type='double3')
        baseline=snapshot(control)
        result=AutoScaleControlCurves(MayaBodyBuildHost()).apply((control,),'Skin')
        assert result.projected_points==0
        assert baseline==snapshot(control)
        row.update(status='passed',points_unchanged=True,no_temporary_nodes=True)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    report['status']='passed' if all(r['status']=='passed' for r in report['cases']) else 'failed'
    (output/'projection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    raise SystemExit(0 if main(Path(sys.argv[1]).resolve())['status']=='passed' else 1)
