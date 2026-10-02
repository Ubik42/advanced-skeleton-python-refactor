"""Source muscle wrap, ordered Skin writes, mirror, loft and lifecycle parity."""
import json,sys,traceback
from maya_original_muscular_reference import ROOT,sample
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/muscular-parity'
def compare(expected,actual):
    assert expected.keys()==actual.keys(),(sorted(expected.keys()-actual.keys()),sorted(actual.keys()-expected.keys()))
    errors={};maximum=0.
    for name,row in expected.items():
        other=actual[name];assert row['kind']==other['kind'];assert len(row['points'])==len(other['points']),(name,'CV count')
        error=max((abs(a-b) for a,b in zip(row['points'],other['points'])),default=0.)
        maximum=max(maximum,error);errors[name]=error
        if 'weights' in row:
            assert row['influences']==other['influences'],(name,row['influences'],other['influences'])
            assert row['method']==other['method']
            for left,right in zip(row['weights'],other['weights']):
                assert len(left)==len(right)
                maximum=max(maximum,max((abs(a-b) for a,b in zip(left,right)),default=0.))
    return maximum,errors

def main(*,standalone=True):
    import maya.standalone
    if standalone:maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_geometry_muscular import MayaMuscularHost
    from adv_py.application.geometry_muscular import CreateMuscular,DeleteMuscular
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running','execution':'standalone' if standalone else 'gui'}
    try:
        native=json.loads((ROOT/'validation/results/original-muscular-reference/reference.json').read_text());assert native['status']=='passed',native.get('traceback')
        c.file(str(ROOT/'validation/results/original-skeleton-geometry-reference/skeleton.mb'),open=True,force=True,executeScriptNodes=False)
        curves,mirrored=CreateMuscular(MayaMuscularHost()).execute();report['counts']={'curves':curves,'mirrored':mirrored}
        maximum,report['errors']=compare(native['curves'],sample());report['poses']={}
        for left,(plug,value) in zip(native['poses'],[('Main.translateX',2.),('Main.scaleY',1.3),('FKShoulder_R.rotateZ',25.),('FKElbow_R.rotateZ',35.)]):
            old=c.getAttr(plug);c.setAttr(plug,value);error,errors=compare(left['curves'],sample());maximum=max(maximum,error);report['poses'][left['name']]=errors;c.setAttr(plug,old)
        created=sample();c.file(rename=str(OUT/'muscular.mb'));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(OUT/'muscular.mb'),open=True,force=True,executeScriptNodes=False)
        error,_=compare(created,sample());maximum=max(maximum,error)
        DeleteMuscular(MayaMuscularHost()).execute();assert not c.objExists('MuscularGeometry')
        c.undo();error,_=compare(created,sample());maximum=max(maximum,error)
        c.redo();assert not c.objExists('MuscularGeometry');report['save_delete_undo_redo']=True
        report['maximum_error']=maximum;assert maximum<1e-4,maximum;report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
        if standalone:maya.standalone.uninitialize()
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
