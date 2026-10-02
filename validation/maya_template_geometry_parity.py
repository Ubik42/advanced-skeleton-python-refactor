"""Concentrated source template geometry parity and complete lifecycle."""
import sys,json,traceback
from template_geometry_fixture import ROOT,setup,sample,poses
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/template-geometry-parity'

def compare(expected,actual):
    assert expected.keys()==actual.keys(),{'missing':sorted(expected.keys()-actual.keys()),'extra':sorted(actual.keys()-expected.keys())}
    maximum=0.;errors={}
    for name,row in expected.items():
        other=actual[name]
        for key in ('faces','materials','influences','settings'):assert row.get(key)==other.get(key),(name,key,row.get(key),other.get(key))
        assert len(row['points'])==len(other['points']),(name,'vertex count')
        error=max((abs(a-b) for a,b in zip(row['points'],other['points'])),default=0.)
        errors[name]=error;maximum=max(maximum,error)
        assert len(row['weights'])==len(other['weights'])
        weight_error=max((abs(a-b) for a,b in zip(row['weights'],other['weights'])),default=0.)
        maximum=max(maximum,weight_error)
    return maximum,errors

def main(kind='mannequin',*,standalone=True):
    import maya.standalone
    if standalone:maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_geometry_mannequin import MayaMannequinHost
    from adv_py.application.geometry_mannequin import CreateMannequin,DeleteMannequin
    from adv_py.adapters.maya_geometry_skeleton import MayaSkeletonGeometryHost
    from adv_py.application.geometry_skeleton import CreateSkeletonGeometry,DeleteSkeletonGeometry
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running','kind':kind,'execution':'standalone' if standalone else 'gui'}
    try:
        native=json.loads((ROOT/('validation/results/original-mannequin-reference/reference.json' if kind=='mannequin' else 'validation/results/original-skeleton-geometry-reference/reference.json')).read_text())
        assert native['status']=='passed',native.get('traceback')
        host,create,delete,group=(MayaMannequinHost,CreateMannequin,DeleteMannequin,'MannequinGeometry') if kind=='mannequin' else (MayaSkeletonGeometryHost,CreateSkeletonGeometry,DeleteSkeletonGeometry,'SkeletonGeometry')
        maximum=0.;report['cases']={}
        for mode in (('normal','alternate_axes','retained_shader') if kind=='mannequin' else ('normal','generic_no_profile')):
            setup(mode);count=create(host()).execute();expected=native[mode] if kind=='mannequin' or mode!='normal' else native
            error,errors=compare(expected['meshes'],sample(group));maximum=max(maximum,error)
            row={'count':count,'errors':errors};report['cases'][mode]=row
            if mode=='normal':
                row['poses']={}
                for left,right in zip(expected['poses'],poses(group)):
                    error,errors=compare(left['meshes'],right['meshes']);maximum=max(maximum,error);row['poses'][left['name']]=errors
            created=sample(group)
            c.file(rename=str(OUT/(kind+'-'+mode+'.mb')));c.file(save=True,type='mayaBinary',force=True)
            c.file(str(OUT/(kind+'-'+mode+'.mb')),open=True,force=True,executeScriptNodes=False)
            error,_=compare(created,sample(group));maximum=max(maximum,error)
            delete(host()).execute();assert not c.objExists(group)
            if kind=='mannequin':assert c.objExists('shaderMannequin')==expected['remaining_shader']
            c.undo();error,_=compare(created,sample(group));maximum=max(maximum,error)
            c.redo();assert not c.objExists(group);row['save_delete_undo_redo']=True
        if kind=='skeleton':
            from adv_py.application.geometry_skeleton import MirrorSkeletonGeometry
            report['mirrors']={}
            for direction in ('R','L'):
                c.file(str(OUT/'skeleton-normal.mb'),open=True,force=True,executeScriptNodes=False)
                c.move(.2,.03,.05,'HumerusBone_'+direction+'.vtx[0]',relative=True,worldSpace=True)
                c.setAttr('HumerusBone_'+('L' if direction=='R' else 'R')+'.scaleX',lock=True)
                count=MirrorSkeletonGeometry(host()).execute(direction)
                error,errors=compare(native['mirrors'][direction],sample(group));maximum=max(maximum,error)
                report['mirrors'][direction]={'count':count,'errors':errors}
        report['maximum_error']=maximum;assert maximum<1e-4,maximum;report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/(kind+'.json')).write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
        if standalone:maya.standalone.uninitialize()
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1] if len(sys.argv)>1 else 'mannequin'))
