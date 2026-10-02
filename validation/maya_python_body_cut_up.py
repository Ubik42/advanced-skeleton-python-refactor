"""Registered Python Body integration of original CutUp dispatch and lifecycle."""
import sys,json,traceback
from geometry_operations_fixture import ROOT,setup_fixture,snapshot
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/python-body-cut-up'
def main():
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds as c
    from adv_py.adapters.maya_geometry_cut_up import MayaGeometryCutUpHost
    from adv_py.adapters.maya_geometry_control_mapping import SourceGeometryControlMapping
    from adv_py.application.geometry_cut_up import CreateGeometryCutUp,DeleteGeometryCutUp
    report={'status':'running'};OUT.mkdir(parents=True,exist_ok=True)
    try:
        base=ROOT/'validation/results/biped-source-bendy-parent-v1-opm/original-biped-current.mb'
        setup_fixture('cut_up',base=base)
        skins={node:c.ls(node,uuid=True)[0] for node in c.ls(type='skinCluster')}
        host=MayaGeometryCutUpHost();mapping=SourceGeometryControlMapping(host)
        report['fk']={joint:mapping.fk(joint) for joint in ('Shoulder_R','Elbow_R','Head_M')}
        assert all(report['fk'].values()),report['fk']
        report['count']=CreateGeometryCutUp(host).execute();assert report['count']==2
        before=snapshot('CutUpGeometry');report['pieces']=list(before)
        assert set(before)=={'FKElbowCutUp1_R','ElbowPart1CutUp1_R'},report['pieces']
        fk=mapping.fk('Elbow_R');old=c.getAttr(fk+'.rotateZ');c.setAttr(fk+'.rotateZ',35)
        after=snapshot('CutUpGeometry')
        report['animated_delta']=max(abs(a-b) for name in before for a,b in zip(before[name]['points'],after[name]['points']))
        assert report['animated_delta']>.01
        c.setAttr(fk+'.rotateZ',old)
        c.select('SourceGeometry',replace=True);CreateGeometryCutUp(MayaGeometryCutUpHost()).execute()
        assert len(snapshot('CutUpGeometry'))==4
        c.file(rename=str(OUT/'registered-body.mb'));c.file(save=True,type='mayaBinary',force=True)
        c.file(str(OUT/'registered-body.mb'),open=True,force=True,executeScriptNodes=False)
        saved=snapshot('CutUpGeometry');DeleteGeometryCutUp(MayaGeometryCutUpHost()).execute();assert not c.objExists('CutUpGeometry')
        c.undo();assert snapshot('CutUpGeometry')==saved
        c.redo();assert not c.objExists('CutUpGeometry')
        assert all(c.ls(node,uuid=True)==[value] for node,value in skins.items())
        from adv_py.adapters.maya_control_mesh import MayaControlMeshHost
        from adv_py.application.control_mesh import CreateControlMesh
        cube=c.polyCube(name='RegisteredMirrorSource',width=4,height=2,depth=2,constructionHistory=False)[0]
        c.select(cube+'.f[5]',mapping.fk('Shoulder_R'),replace=True)
        mirror=CreateControlMesh(MayaControlMeshHost()).execute('AdvPy_Global',mirror=True)
        assert len(mirror)==2
        report['registered_fk_mirror']=True
        c.undo();assert all(not c.objExists(item.shape_name) for item in mirror)
        c.redo();assert all(c.objExists(item.shape_name) for item in mirror)
        report['skin_preserved']=True;report['append_save_delete_undo_redo']=True;report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));maya.standalone.uninitialize()
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
