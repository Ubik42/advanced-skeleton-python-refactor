"""Original scan-pivot-to-Fit placement and fat passes on one actual Fit scene."""
from pathlib import Path
import json,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def snapshot():
    from maya import cmds as c
    return {'joints':{node:{'matrix':c.xform(node,query=True,worldSpace=True,matrix=True),
        'fat':[c.getAttr(node+'.'+attr) if c.objExists(node+'.'+attr) else None
               for attr in ('fat','fatFront','fatWidth')]}
        for node in c.listRelatives('FitSkeleton',allDescendents=True,type='joint',fullPath=True)},
        'constraints':sorted(c.listRelatives('asFitConstraints',children=True) or []),
        'center_lock':c.getAttr('FitSkeleton.lockCenterJoints')}


def fixture(scene,fingers):
    from maya import cmds as c
    c.file(str(scene),open=True,force=True,executeScriptNodes=False)
    c.selectMode(object=True)
    if fingers:
        for digit,finger in enumerate(('Index','Middle','Ring','Pinky','Thumb')):
            base=c.xform(finger+'Finger1',query=True,worldSpace=True,translation=True)
            tip=c.xform(finger+'Finger4',query=True,worldSpace=True,translation=True)
            for segment,point in ((1,base),(4,tip)):
                node='asFitPivot'+finger+'Finger'+str(segment)
                if c.objExists(node):c.delete(c.ls(node,long=True))
                c.createNode('transform',name=node,parent='asFitPivotsFingers')
                c.xform(node,worldSpace=True,translation=(point[0]-.2,point[1]+.3,point[2]+digit*.04))
            curve='FingerCurve'+finger
            if c.objExists(curve):c.delete(c.ls(curve,long=True))
            points=[c.xform(finger+'Finger'+str(i),query=True,worldSpace=True,translation=True) for i in range(1,5)]
            points=[(p[0]-.2,p[1]+.3,p[2]+digit*.04) for p in points]
            node=c.curve(name=curve,degree=1,point=points)
            c.parent(node,'asFitPivotsFingers')
    c.select('Root')


def main(output):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c,mel
    from adv_py.adapters.maya_fit import MayaFitJointHost
    from adv_py.adapters.maya_fit_auto_place_positions import from_scan_curves,set_fat
    output.mkdir(parents=True,exist_ok=True)
    mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";')
    scene=ROOT/'validation/results/fit-auto-place-gui-selection/before-cleanup.mb'
    report={'status':'running','cases':[]}
    for fingers in (False,True):
        row={'fingers':fingers};report['cases'].append(row)
        try:
            fixture(scene,fingers)
            mel.eval('asFitAutoPlaceFromScanCurves; asFitAutoPlaceSetFat;')
            native=snapshot()
            fixture(scene,fingers);before=snapshot()
            host=MayaFitJointHost()
            with host.transaction('Native scan pivot Fit placement'):
                from_scan_curves(host);set_fat(host)
            python=snapshot()
            error=max(abs(a-b) for node,values in native['joints'].items()
                      for a,b in zip(values['matrix'],python['joints'][node]['matrix']))
            fat_error=max(abs(a-b) for node,values in native['joints'].items()
                          for a,b in zip(values['fat'],python['joints'][node]['fat']) if a is not None)
            assert error<=1e-4 and fat_error<=1e-4,(error,fat_error)
            assert native['constraints']==python['constraints']
            assert native['center_lock']==python['center_lock']
            c.undo();undone=snapshot()
            undo=max(abs(a-b) for node,values in before['joints'].items()
                     for a,b in zip(values['matrix'],undone['joints'][node]['matrix']))
            assert undo<=1e-8,undo
            c.redo()
            row.update(status='passed',joint_error=error,fat_error=fat_error,undo_error=undo,
                       constraints=len(python['constraints']))
        except Exception:row.update(status='failed',error=traceback.format_exc())
    row={'case':'placement_failure_rollback'};report['cases'].append(row)
    try:
        fixture(scene,True)
        # History projections create their output DAG children lazily when
        # opened in standalone. Evaluate this unchanged input before taking
        # the identity baseline; those outputs are not placement-created nodes.
        for node in c.ls(type='polyProjectCurve') or []:
            c.dgeval(node)
        for node in c.ls('asFitProjection*',type='transform') or []:
            c.getAttr(node+'.boundingBoxMin')
            c.getAttr(node+'.boundingBoxMax')
        before=snapshot()
        uuids={c.ls(node,uuid=True)[0]:node for node in c.ls(long=True)}
        original=c.geometryConstraint
        def fail(*args,**kwargs):
            raise RuntimeError('Injected failure after Root and finger constraint writes')
        c.geometryConstraint=fail
        try:
            host=MayaFitJointHost()
            try:
                with host.transaction('Failed native pivot placement'):
                    from_scan_curves(host)
            except RuntimeError as error:
                assert 'Injected failure' in str(error),str(error)
            else:raise AssertionError('Failure was not reached')
        finally:c.geometryConstraint=original
        after=snapshot()
        error=max(abs(a-b) for node,values in before['joints'].items()
                  for a,b in zip(values['matrix'],after['joints'][node]['matrix']))
        assert error<=1e-8,error
        assert before['constraints']==after['constraints']
        assert before['center_lock']==after['center_lock']
        current={c.ls(node,uuid=True)[0]:node for node in c.ls(long=True)}
        row['created_nodes']=[current[key] for key in current.keys()-uuids.keys()]
        row['removed_nodes']=[uuids[key] for key in uuids.keys()-current.keys()]
        assert current.keys()==uuids.keys(),(row['created_nodes'],row['removed_nodes'])
        row.update(status='passed',joint_error=error,scene_nodes_restored=True)
    except Exception:row.update(status='failed',error=traceback.format_exc())
    report['status']='passed' if all(row['status']=='passed' for row in report['cases']) else 'failed'
    (output/'positions.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).resolve()))
