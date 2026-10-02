"""Complete native template chains on registered Python Body and isolated actors."""
import sys,json,traceback
from template_geometry_fixture import ROOT
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/python-body-template-geometry'
def main():
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_geometry_mannequin import MayaMannequinHost
    from adv_py.adapters.maya_geometry_skeleton import MayaSkeletonGeometryHost
    from adv_py.adapters.maya_geometry_muscular import MayaMuscularHost
    from adv_py.application.geometry_mannequin import CreateMannequin,DeleteMannequin
    from adv_py.application.geometry_skeleton import CreateSkeletonGeometry,DeleteSkeletonGeometry
    from adv_py.application.geometry_muscular import CreateMuscular,DeleteMuscular
    from adv_py.adapters.maya_geometry_control_mapping import SourceGeometryControlMapping
    from adv_py.adapters.maya_geometry_cut_up import MayaGeometryCutUpHost
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running'}
    try:
        base=ROOT/'validation/results/biped-source-bendy-parent-v1-opm/original-biped-current.mb'
        c.file(str(base),open=True,force=True,executeScriptNodes=False)
        protected={node:c.ls(node,uuid=True)[0] for node in c.ls(type='skinCluster')}
        report['mannequin']=CreateMannequin(MayaMannequinHost()).execute()
        report['skeleton']=CreateSkeletonGeometry(MayaSkeletonGeometryHost()).execute()
        report['muscular']=CreateMuscular(MayaMuscularHost()).execute()
        mapping=SourceGeometryControlMapping(MayaGeometryCutUpHost());fk=mapping.fk('Elbow_R');old=c.getAttr(fk+'.rotateZ')
        before=c.xform('UlnaBone_R.vtx[*]',q=True,ws=True,t=True)
        c.setAttr(fk+'.rotateZ',35)
        report['animated']=c.xform('UlnaBone_R.vtx[*]',q=True,ws=True,t=True)!=before
        assert report['animated']
        c.setAttr(fk+'.rotateZ',old)
        c.file(rename=str(OUT/'registered-body.mb'));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(OUT/'registered-body.mb'),open=True,force=True,executeScriptNodes=False)
        for delete,host,group in [(DeleteMuscular,MayaMuscularHost,'MuscularGeometry'),(DeleteSkeletonGeometry,MayaSkeletonGeometryHost,'SkeletonGeometry'),(DeleteMannequin,MayaMannequinHost,'MannequinGeometry')]:
            delete(host()).execute();assert not c.objExists(group);c.undo();assert c.objExists(group);c.redo();assert not c.objExists(group)
        assert all(c.ls(node,uuid=True)==[uuid] for node,uuid in protected.items())
        report['skin_preserved']=True;report['save_delete_undo_redo']=True
        # An isolated native Body exercises all three adapters' namespace boundary.
        source=ROOT/'validation/results/original-bendy-reference/original-bendy-reference.mb'
        c.file(new=True,force=True);c.file(str(source),i=True,namespace='GeometryActor',executeScriptNodes=False)
        c.namespace(add='UnrelatedEditor');c.namespace(set=':UnrelatedEditor')
        foreign=c.polyCube(name='ForeignGeometry',constructionHistory=False)[0];uuid=c.ls(foreign,uuid=True)
        report['namespace']={}
        for create,host,group in [(CreateMannequin,MayaMannequinHost,'MannequinGeometry'),(CreateSkeletonGeometry,MayaSkeletonGeometryHost,'SkeletonGeometry'),(CreateMuscular,MayaMuscularHost,'MuscularGeometry')]:
            report['namespace'][group]=create(host('GeometryActor')).execute();assert c.objExists(':GeometryActor:'+group)
            assert c.namespaceInfo(currentNamespace=True).strip(':')=='UnrelatedEditor';assert c.ls(foreign,uuid=True)==uuid
        for delete,host,group in [(DeleteMuscular,MayaMuscularHost,'MuscularGeometry'),(DeleteSkeletonGeometry,MayaSkeletonGeometryHost,'SkeletonGeometry'),(DeleteMannequin,MayaMannequinHost,'MannequinGeometry')]:
            delete(host('GeometryActor')).execute();assert not c.objExists(':GeometryActor:'+group)
            c.undo();assert c.objExists(':GeometryActor:'+group);c.redo();assert not c.objExists(':GeometryActor:'+group)
            assert c.ls(foreign,uuid=True)==uuid
        report['namespace_preserved']=True;report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));maya.standalone.uninitialize()
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
