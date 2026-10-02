"""Geometry operations on an independent character with unrelated active namespace."""
import sys,json,traceback
from geometry_operations_fixture import ROOT,setup_fixture
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/geometry-operations-namespace'
def main():
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_geometry_boolean import MayaBooleanHost
    from adv_py.adapters.maya_geometry_warp import MayaWarpHost
    from adv_py.adapters.maya_geometry_cut_up import MayaGeometryCutUpHost
    from adv_py.application.geometry_boolean import CreateBoolean,DeleteBoolean
    from adv_py.application.geometry_warp import CreateWarp,DeleteWarp
    from adv_py.application.geometry_cut_up import CreateGeometryCutUp,DeleteGeometryCutUp
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running'}
    try:
        for kind,host,create,delete,group in [('boolean',MayaBooleanHost,CreateBoolean,DeleteBoolean,'BoolGeometry'),('warp',MayaWarpHost,CreateWarp,DeleteWarp,'WarpGeometry'),('cut_up',MayaGeometryCutUpHost,CreateGeometryCutUp,DeleteGeometryCutUp,'CutUpGeometry')]:
            setup_fixture(kind);fixture=OUT/(kind+'-input.mb')
            c.file(rename=str(fixture));c.file(save=True,type='mayaBinary',force=True)
            c.file(new=True,force=True);c.file(str(fixture),i=True,namespace='GeometryActor',executeScriptNodes=False)
            c.namespace(add='UnrelatedEditor');c.namespace(set=':UnrelatedEditor')
            foreign=c.polyCube(name='ForeignGeometry',constructionHistory=False)[0];foreign_uuid=c.ls(foreign,uuid=True)
            c.select(':GeometryActor:SourceGeometry',replace=True)
            count=create(host('GeometryActor')).execute();assert count>0
            assert c.namespaceInfo(currentNamespace=True).strip(':')=='UnrelatedEditor'
            assert c.objExists(':GeometryActor:'+group)
            c.file(rename=str(OUT/(kind+'-created.mb')));c.file(save=True,type='mayaBinary',force=True)
            delete(host('GeometryActor')).execute();assert not c.objExists(':GeometryActor:'+group)
            c.undo();assert c.objExists(':GeometryActor:'+group)
            c.redo();assert not c.objExists(':GeometryActor:'+group)
            assert c.ls(foreign,uuid=True)==foreign_uuid
            report[kind]={'count':count,'foreign_preserved':True,'namespace_restored':True,'delete_undo_redo':True}
        report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));maya.standalone.uninitialize()
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())

