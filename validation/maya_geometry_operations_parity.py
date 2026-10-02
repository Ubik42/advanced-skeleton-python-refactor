"""Source geometry operations comparison and complete lifecycle."""
import sys,json,traceback
from geometry_operations_fixture import ROOT,setup_fixture,snapshot,poses
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/geometry-operations-parity'


def main(*,standalone=True):
    import maya.standalone
    if standalone:maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_geometry_boolean import MayaBooleanHost
    from adv_py.adapters.maya_geometry_warp import MayaWarpHost
    from adv_py.adapters.maya_geometry_cut_up import MayaGeometryCutUpHost
    from adv_py.application.geometry_boolean import CreateBoolean,DeleteBoolean
    from adv_py.application.geometry_warp import CreateWarp,DeleteWarp
    from adv_py.application.geometry_cut_up import CreateGeometryCutUp,DeleteGeometryCutUp
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running','execution':'standalone' if standalone else 'gui'}
    native=json.loads((ROOT/'validation/results/original-geometry-operations/reference.json').read_text(encoding='utf8'))
    def compare(reference,actual):
        assert reference.keys()==actual.keys(),(list(reference),list(actual))
        errors={}
        for name,row in reference.items():
            other=actual[name]
            for key in ('faces','materials','uv_sets','color_sets','render'):assert row[key]==other[key],(name,key,row[key],other[key])
            assert len(row['points'])==len(other['points'])
            errors[name]=max(abs(a-b) for a,b in zip(row['points'],other['points']))
        return errors
    try:
        assert native['status']=='passed',native.get('traceback')
        for kind,host_type,create_type,delete_type,group in [
            ('boolean',MayaBooleanHost,CreateBoolean,DeleteBoolean,'BoolGeometry'),
            ('warp',MayaWarpHost,CreateWarp,DeleteWarp,'WarpGeometry'),
            ('cut_up',MayaGeometryCutUpHost,CreateGeometryCutUp,DeleteGeometryCutUp,'CutUpGeometry')]:
            setup_fixture(kind);host=host_type();count=create_type(host).execute()
            row={'count':count,'first_errors':compare(native[kind]['first'],snapshot(group))};report[kind]=row
            assert c.getAttr('SourceGeometry.visibility')==native[kind]['source_visibility']
            if kind=='cut_up':
                row['faces']={name:len(data['faces']) for name,data in snapshot(group).items()}
            row['pose_errors']={sample['name']:compare(sample['meshes'],actual['meshes'])
                for sample,actual in zip(native[kind]['poses'],poses(group))}
            c.select('SourceGeometry',replace=True)
            append_error=None
            try:create_type(host_type()).execute()
            except Exception as error:append_error=error
            if 'append_error' in native[kind]:
                assert append_error is not None,'Python append succeeded where source failed'
                row['source_append_failure_preserved']=True
            elif append_error is not None:raise append_error
            row['appended_errors']=compare(native[kind]['appended'],snapshot(group))
            c.file(rename=str(OUT/(kind+'.mb')));c.file(save=True,type='mayaBinary',force=True)
            c.file(str(OUT/(kind+'.mb')),open=True,force=True,executeScriptNodes=False)
            row['reopen_errors']=compare(native[kind]['appended'],snapshot(group))
            delete_type(host_type()).execute();assert not c.objExists(group)
            c.undo();assert c.objExists(group)
            row['undo_errors']=compare(native[kind]['appended'],snapshot(group))
            c.redo();assert not c.objExists(group)
            row['delete_undo_redo']=True
        numeric=[]
        for kind in ('boolean','warp','cut_up'):
            row=report[kind]
            for key in ('first_errors','appended_errors','reopen_errors','undo_errors'):numeric.extend(row[key].values())
            for errors in row['pose_errors'].values():numeric.extend(errors.values())
        report['maximum_error']=max(numeric,default=0.)
        assert report['maximum_error']<1e-4,report['maximum_error']
        report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'parity.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps(report,indent=2))
        if standalone:maya.standalone.uninitialize()
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
