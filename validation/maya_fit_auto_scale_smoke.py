"""Concentrated AutoScale lifecycle, eye-component, SoftMod and namespace run."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main(output):
    output=output.resolve()
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.application.fit_auto_scale import AutoScaleFit
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.product.maya_panel_controller import MayaPanelController
    from adv_py.adapters.maya_preparation_objects import MayaPreparationObjectsHost
    from adv_py.core.preparation_objects import PreparationObjectRole
    from maya_original_fit_auto_scale_parity import fixture,snapshot
    output.mkdir(parents=True,exist_ok=True);report={'status':'running','cases':[]}
    for case in ('ordinary','scaled_fit','multiple_skin','eye_object','eye_components','softmod'):
        skin,all_objects,eye=fixture(case);before=snapshot()
        c.undoInfo(state=True)
        result=AutoScaleFit(MayaFitJointHost()).apply(skin=skin,all_objects=all_objects,right_eye=eye)
        after=snapshot()
        assert len(result.plan.positions)==len(before['joints'])
        assert after['container_scale']==(1.,1.,1.)
        assert not after['softmods'] and not (c.ls('AdvPy_FitAutoScale*') or [])
        assert after['selection']==before['selection']
        c.undo();undone=snapshot()
        assert undone['joints']==before['joints'],(case,'Undo did not restore Fit')
        c.redo();redone=snapshot()
        assert redone['joints']==after['joints'],(case,'Redo did not restore scaled Fit')
        report['cases'].append({'case':case,'factor':result.plan.factor,'eye_placed':result.eye_placed,
            'joints':len(result.plan.positions),'undo_redo':True})
    skin,all_objects,eye=fixture('ordinary');before=snapshot()
    # Invalid mesh passes Fit reads but fails before a mutation transaction.
    try:AutoScaleFit(MayaFitJointHost()).apply(skin=('MissingSkin',))
    except ValueError:pass
    else:raise AssertionError('Missing Skin was accepted')
    assert snapshot()['joints']==before['joints']
    # This fails after scaling and CV writes; the entire chunk must roll back.
    try:AutoScaleFit(MayaFitJointHost()).apply(skin=skin,right_eye=(skin[0]+'.vtx[999999]',))
    except (ValueError,RuntimeError):pass
    else:raise AssertionError('Invalid eye component was accepted')
    assert snapshot()['joints']==before['joints'] and not (c.ls('AdvPy_FitAutoScale*') or [])
    report['rollback']=True
    c.file(new=True,force=True)
    c.file(str(ROOT/'validation/results/source-spline-multi.ma'),i=True,namespace='ScaleRig',executeScriptNodes=False)
    mesh=c.polyCube(name='ExternalScaleSkin',height=30,width=10,depth=5)[0]
    c.move(0,15,0,mesh);c.makeIdentity(mesh,apply=True,translate=True,rotate=True,scale=True)
    c.delete(mesh,constructionHistory=True)
    records=MayaPreparationObjectsHost('ScaleRig')
    records.write_objects(PreparationObjectRole.SKIN,tuple(c.ls(mesh,long=True)))
    result=MayaPanelController().fit_auto_scale('ScaleRig',interactive=False)
    assert c.getAttr('ScaleRig:FitSkeleton.scale')[0]==(1.,1.,1.)
    assert not (c.ls('ScaleRig:AdvPy_FitAutoScale*') or [])
    report['namespaced_external_skin']={'joints':len(result.plan.positions),'factor':result.plan.factor}
    c.file(rename=str(output/'auto-scale.mb'));c.file(save=True,type='mayaBinary',force=True)
    positions=c.xform('ScaleRig:Root',query=True,worldSpace=True,translation=True)
    c.file(str(output/'auto-scale.mb'),open=True,force=True,executeScriptNodes=False)
    assert c.xform('ScaleRig:Root',query=True,worldSpace=True,translation=True)==positions
    report['saved_reopened']=True
    report['namespaced_cases']=[]
    for case in ('multiple_skin','eye_components','softmod'):
        skin,all_objects,eye=fixture(case)
        c.delete('FitSkeleton')
        c.file(str(ROOT/'validation/results/source-spline-multi.ma'),i=True,
               namespace='ScaleRig',executeScriptNodes=False)
        records=MayaPreparationObjectsHost('ScaleRig')
        for role,names in ((PreparationObjectRole.SKIN,skin),
                           (PreparationObjectRole.ALL,all_objects),
                           (PreparationObjectRole.RIGHT_EYE,eye)):
            records.write_objects(role,tuple(c.ls(names,long=True)))
        c.select(skin[0],replace=True)
        before=tuple(c.xform('ScaleRig:Root',query=True,worldSpace=True,matrix=True))
        result=MayaPanelController().fit_auto_scale('ScaleRig',interactive=False)
        after=tuple(c.xform('ScaleRig:Root',query=True,worldSpace=True,matrix=True))
        assert not c.ls(type='softMod') and not c.ls('ScaleRig:AdvPy_FitAutoScale*')
        c.undo()
        assert tuple(c.xform('ScaleRig:Root',query=True,worldSpace=True,matrix=True))==before
        c.redo()
        assert tuple(c.xform('ScaleRig:Root',query=True,worldSpace=True,matrix=True))==after
        report['namespaced_cases'].append({'case':case,'factor':result.plan.factor,
                                          'eye_placed':result.eye_placed,'undo_redo':True})
    report['status']='passed'
    (output/'auto-scale.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS Fit auto scale lifecycle',report)


if __name__=='__main__':main(Path(sys.argv[1]))
