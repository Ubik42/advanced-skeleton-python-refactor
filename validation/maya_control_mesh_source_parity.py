"""Actual source Control Mesh mirror and batch fixtures."""
import json,sys,traceback
from geometry_operations_fixture import ROOT,setup_fixture,snapshot
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'validation/results/control-mesh-source-parity'

def setup(mode):
    from maya import cmds as c
    setup_fixture('cut_up')
    if mode!='batch':
        source=c.polyCube(name='MirrorSource',width=4,height=2,depth=2,constructionHistory=False)[0]
        c.sets(source,edit=True,forceElement='SourceGreenSG')
        c.sets(source+'.f[4]',edit=True,forceElement='SourceBlueSG')
        if mode=='face_mirror':c.sets(['FKShoulder_R','FKShoulder_L'],name='FaceControlSet')
        c.select(source+'.f[5]','Shoulder_R' if mode=='joint_mirror' else 'FKShoulder_R',replace=True)

def sample():
    from maya import cmds as c
    from maya.api import OpenMaya as om
    rows={}
    for shape in c.ls('*MeshCtrl*',type='mesh',noIntermediate=True,long=True) or []:
        fn=om.MFnMesh(om.MSelectionList().add(shape).getDagPath(0))
        shaders,slots=fn.getConnectedShaders(0)
        rows[shape.rsplit('|',1)[-1]]={
            'points':c.xform(shape+'.vtx[*]',q=True,ws=True,t=True),
            'faces':[list(fn.getPolygonVertices(i)) for i in range(fn.numPolygons)],
            'normals':[list(n) for n in fn.getNormals(om.MSpace.kObject)],
            'uvs':{name:[list(v) for v in fn.getUVs(name)] for name in fn.getUVSetNames()},
            'colors':{name:[list(v) for v in fn.getColors(name)] for name in fn.getColorSetNames()},
            'materials':[om.MFnDependencyNode(shaders[i]).name() if i>=0 else None for i in slots]}
    return rows

def main(native=False):
    from maya import cmds as c,mel
    OUT.mkdir(parents=True,exist_ok=True);report={'status':'running'};maximum_error=0.
    try:
        if native:
            c.optionVar(intValue=('asHaveRanThisVersion',1));c.optionVar(intValue=('asDock',0))
            mel.eval('source "'+(ROOT/'local/adv_6_925/AdvancedSkeleton.mel').as_posix()+'";');mel.eval('AdvancedSkeleton;')
        else:reference=json.loads((OUT/'reference.json').read_text())
        for mode in ('batch','mirror','face_mirror','joint_mirror'):
            setup(mode)
            if native:
                c.checkBox('asCreateControlMeshMirrorCheckBox',edit=True,value=True)
                mel.eval('asCreateControlMeshes;' if mode=='batch' else 'asCreateControlMesh;')
            else:
                from adv_py.application.control_mesh import CreateControlMesh,CreateControlMeshes
                from adv_py.adapters.maya_control_mesh import MayaControlMeshHost
                host=MayaControlMeshHost()
                if mode=='batch':CreateControlMeshes(host).execute('Main',tuple(c.ls('FK*',type='transform')))
                else:CreateControlMesh(host).execute('Main',mirror=True)
            actual=sample();assert actual,mode
            report[mode]=actual
            if not native:
                expected=reference[mode];assert expected.keys()==actual.keys(),(mode,list(expected),list(actual))
                for shape,row in expected.items():
                    for key in ('faces','materials'):assert row[key]==actual[shape][key],(mode,shape,key)
                    for key in ('points','normals','uvs','colors'):
                        def flat(value):
                            if isinstance(value,dict):return [x for name in sorted(value) for x in flat(value[name])]
                            if isinstance(value,list):return [x for item in value for x in flat(item)]
                            return [value]
                        left,right=flat(row[key]),flat(actual[shape][key]);assert len(left)==len(right),(mode,shape,key)
                        error=max((abs(a-b) for a,b in zip(left,right)),default=0)
                        maximum_error=max(maximum_error,error)
                        assert error<1e-4,(mode,shape,key,error)
        if not native:
            setup('mirror');fixture=OUT/'namespace-input.mb'
            c.file(rename=str(fixture));c.file(save=True,type='mayaBinary',force=True)
            c.file(new=True,force=True);c.file(str(fixture),i=True,namespace='GeometryActor',executeScriptNodes=False)
            c.namespace(add='UnrelatedEditor');c.namespace(set=':UnrelatedEditor')
            foreign=c.polyCube(name='ForeignGeometry',constructionHistory=False)[0];uuid=c.ls(foreign,uuid=True)
            c.select(':GeometryActor:MirrorSource.f[5]',':GeometryActor:FKShoulder_R',replace=True)
            plan=CreateControlMesh(MayaControlMeshHost()).execute('GeometryActor:Main',mirror=True)
            assert len(plan)==2
            assert c.namespaceInfo(currentNamespace=True).strip(':')=='UnrelatedEditor'
            assert c.ls(foreign,uuid=True)==uuid
            c.undo();assert all(not c.objExists(item.shape_name) for item in plan)
            c.redo();assert all(c.objExists(item.shape_name) for item in plan)
            report['namespace_lifecycle']={'count':len(plan),'foreign_preserved':True,'undo_redo':True}
        if not native:report['maximum_error']=maximum_error
        report['status']='passed'
    except Exception:report['status']='failed';report['traceback']=traceback.format_exc()
    finally:
        (OUT/('reference.json' if native else 'parity.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
        print(report.get('status'),report.get('traceback',''))
        if native:c.quit(force=True)
    return report['status']=='passed'

if __name__=='__main__':
    import maya.standalone
    maya.standalone.initialize(name='python')
    success=main();maya.standalone.uninitialize();raise SystemExit(0 if success else 1)

