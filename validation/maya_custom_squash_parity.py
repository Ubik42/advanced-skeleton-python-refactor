"""One-process native Squash graph, deformation and lifecycle comparison."""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "validation/results/custom-squash-current"


def source_procedures(mel):
    from adv_migration.mel_inventory import PROC_HEADER, _matching_brace
    source = (ROOT / "local/adv_6_925/AdvancedSkeleton.mel").read_text(encoding="utf-8-sig")
    wanted = {"asMayaVersionAsFloat", "asDeformer", "asCreateSquashDeformSetup"}
    found = set()
    for match in PROC_HEADER.finditer(source):
        if match["name"] in wanted:
            end = _matching_brace(source, match.end() - 1)
            mel.eval(source[match.start():end + 1])
            found.add(match["name"])
    assert found == wanted, found


def setup(side, namespace=""):
    from maya import cmds as c
    c.file(new=True, force=True)
    c.undoInfo(state=True)
    c.optionVar(intValue=("deformationUseComponentTags", 0))
    if namespace:
        c.namespace(add=namespace)
        c.namespace(set=namespace)
    nodes = {name: c.createNode("transform", name=name)
             for name in ("MotionSystem", "DeformationSystem", "Main", "buildPose")}
    c.addAttr(nodes["buildPose"], longName="udAttr", dataType="string")
    c.setAttr(nodes["buildPose"] + ".udAttr", "", type="string")
    control_set = c.sets(empty=True, name="ControlSet")
    c.sets(nodes["Main"], add=control_set)
    c.select(clear=True)
    parent = c.joint(name="Parent" + side, position=(0, 2, 0))
    c.parent(parent, nodes["DeformationSystem"])
    c.setAttr(parent + ".rotate", 15, 10, 5, type="float3")
    c.select(clear=True)
    mesh = c.polyCube(name="Mesh", width=2, height=4, depth=2,
                      subdivisionsX=3, subdivisionsY=8, subdivisionsZ=3)[0]
    c.xform(mesh, worldSpace=True, translation=(-3 if side == "_R" else 3, 6, 0))
    c.namespace(set=":")
    return mesh, parent


def source_setup(mesh, parent, side):
    from maya import cmds as c, mel
    from adv_py.adapters.maya_squash_controller import _BOX_POINTS, _CROSS_POINTS
    name = "Detail"
    c.createNode("transform", name="CustomSystem", parent="MotionSystem")
    c.addAttr("Main", longName="customVis", attributeType="bool", defaultValue=1)
    c.connectAttr("Main.customVis", "CustomSystem.visibility")
    c.curve(name=name + side, degree=1, point=_BOX_POINTS)
    c.createNode("transform", name=name + "Attach" + side, parent="CustomSystem")
    c.curve(name=name + "Base" + side, degree=1, point=_CROSS_POINTS)
    meshes = [mesh] if isinstance(mesh, str) else mesh
    boxes = [c.xform(item, query=True, worldSpace=True, boundingBox=True) for item in meshes]
    box = [min(b[i] for b in boxes) for i in range(3)] + [max(b[i+3] for b in boxes) for i in range(3)]
    selection = " ".join(meshes)
    radius = sum(box[i+3]-box[i] for i in range(3))/3.
    scale = radius/4./.4
    c.scale(scale, scale, scale, name+"Base"+side+".cv[0:4]", relative=True, pivot=(0,0,0))
    mel.eval('global string $gMove="moveSuperContext"; global string $gSelect="selectSuperContext";')
    mel.eval('asCreateSquashDeformSetup "Detail" "'+side+'" '+str(-1 if side=="_L" else 1)+' 1 "'+parent+'" "" "'+selection+'" {0,0,0};')


def sample(side, namespace=""):
    from maya import cmds as c
    prefix = namespace + ":" if namespace else ""
    n = lambda token: prefix + "Detail" + token + side
    meshes = [prefix + "Mesh"]
    if c.objExists(prefix + "MeshOther"):
        meshes.append(prefix + "MeshOther")
    vertices = [value for mesh in meshes for value in
                c.xform(mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)]
    return {"vertices": vertices,
            "joints": [c.xform(n("IKX"+str(i)), query=True, worldSpace=True, matrix=True) for i in range(11)],
            "control": c.xform(n(""), query=True, worldSpace=True, matrix=True),
            "base": c.xform(n("Base"), query=True, worldSpace=True, matrix=True),
            "lattice": c.xform(n("FfdLattice")+".pt[*][*][*]", query=True, worldSpace=True, translation=True)}


def error(left, right):
    def flatten(x):
        for item in x:
            if isinstance(item, (tuple, list)):
                yield from flatten(item)
            else:
                yield float(item)
    result = {}
    for key in left:
        a,b = list(flatten(left[key])),list(flatten(right[key]))
        assert len(a)==len(b),(key,len(a),len(b))
        result[key]=max((abs(x-y) for x,y in zip(a,b)),default=0.)
    return result


POSES = ({}, {"translateX":1.}, {"translateY":.5, "translateZ":-.2},
         {"rotateX":30.}, {"rotateY":15., "rotateZ":-10.},
         {"translateX":-1., "volume":5.}, {"translateX":1., "stretch":0},
         {"translateY":.5,"rotateX":30.,"bend":0})


def pose_samples(side, namespace=""):
    from maya import cmds as c
    prefix = namespace+":" if namespace else ""
    control = prefix+"Detail"+side
    defaults={"translateX":0.,"translateY":0.,"translateZ":0.,"rotateX":0.,"rotateY":0.,"rotateZ":0.,"volume":10.,"stretch":1,"squash":1,"bend":1}
    rows=[]
    for pose in POSES:
        for attr,value in dict(defaults,**pose).items():c.setAttr(control+"."+attr,value)
        rows.append(sample(side,namespace))
    for attr,value in defaults.items():c.setAttr(control+"."+attr,value)
    return rows


def main(*, standalone=True, quit_on_finish=False):
    import maya.standalone
    if standalone:maya.standalone.initialize(name="python")
    from maya import cmds as c, mel
    from adv_py.adapters.maya_squash_controller import MayaSquashControllerHost
    from adv_py.application.squash_controller import CreateSquashController, DeleteSquashController
    OUT.mkdir(parents=True,exist_ok=True)
    report={"status":"running","cases":{},"execution":"standalone" if standalone else "graphical Maya"}
    try:
        source_procedures(mel)
        for side in ("_R","_L"):
            mesh,parent=setup(side);source_setup(mesh,parent,side)
            expected=pose_samples(side)
            mesh,parent=setup(side)
            c.select(mesh,replace=True)
            if side == "_R":
                plans=CreateSquashController(MayaSquashControllerHost()).apply("Detail",mirror=False)
                assert plans[0].side==side,plans[0].side
            else:
                from adv_py.core.squash_controller import SquashSelection, plan_squash_controller
                bounds=tuple(c.xform(mesh,query=True,worldSpace=True,boundingBox=True))
                selection=SquashSelection((mesh,),mesh,bounds,parent,side,True,False)
                plan=plan_squash_controller(selection,"Detail")
                host=MayaSquashControllerHost()
                with host.transaction("Mirror squash"):
                    with host.squash_build_pose_session(plan):host.create_squash_controller(plan)
            actual=pose_samples(side)
            errors=[error(a,b) for a,b in zip(expected,actual)]
            maximum=max(v for row in errors for v in row.values())
            report["cases"][side]={"errors":errors,"maximum_error":maximum}
            assert maximum<1e-4,(side,errors)
            before=sample(side)
            scene=OUT/("detail"+side+".mb")
            c.file(rename=str(scene));c.file(save=True,type="mayaBinary",force=True)
            c.file(str(scene),open=True,force=True,executeScriptNodes=False)
            assert max(error(before,sample(side)).values())<1e-4
            c.select("Detail"+side,replace=True)
            DeleteSquashController(MayaSquashControllerHost()).apply("Detail"+side)
            assert not c.objExists("DetailAttach"+side)
            c.undo();assert max(error(before,sample(side)).values())<1e-4
            c.redo();assert not c.objExists("DetailAttach"+side)
            report["cases"][side]["save_delete_undo_redo"]=True
        # Multiple objects use the exact source FFD setup, not a one-mesh approximation.
        def multi_setup():
            mesh,parent=setup("_R")
            second=c.polyCube(name="MeshOther",width=1,height=2,depth=1,
                              subdivisionsX=2,subdivisionsY=4,subdivisionsZ=2)[0]
            c.xform(second,worldSpace=True,translation=(-5,7,0))
            return [mesh,second],parent
        meshes,parent=multi_setup();source_setup(meshes,parent,"_R")
        native_multi=sample("_R")
        expected=pose_samples("_R")
        meshes,parent=multi_setup();c.select(meshes,replace=True)
        multi_plans=CreateSquashController(MayaSquashControllerHost()).apply("Detail",mirror=False)
        actual_multi=sample("_R")
        (OUT/"multi-diagnostic.json").write_text(json.dumps({"source":native_multi,"python":actual_multi,
            "plan_bounds":multi_plans[0].bounds,"plan_vertices":multi_plans[0].vertices}),encoding="utf-8")
        errors=[error(a,b) for a,b in zip(expected,pose_samples("_R"))]
        maximum=max(v for row in errors for v in row.values())
        assert maximum<1e-4,errors
        report["cases"]["multi_mesh"]={"maximum_error":maximum,"errors":errors}
        # Shape components and renamed namespace retain their real node identities.
        mesh,parent=setup("_R",namespace="Actor")
        c.select("Actor:MeshShape.vtx[0:30]",replace=True)
        plans=CreateSquashController(MayaSquashControllerHost(namespace="Actor")).apply("Detail",mirror=False)
        assert all(v.startswith("|Actor:Mesh.vtx[") for v in plans[0].vertices)
        prior=sample("_R","Actor")
        c.namespace(rename=("Actor","Renamed"))
        host=MayaSquashControllerHost(namespace="Renamed")
        DeleteSquashController(host).apply("Detail_R")
        assert not c.objExists("Renamed:DetailAttach_R")
        c.undo();assert max(error(prior,sample("_R","Renamed")).values())<1e-4
        c.redo();assert not c.objExists("Renamed:DetailAttach_R")
        report["cases"]["shape_namespace"]={"create_namespace_rename_delete_undo_redo":True}
        # Mirrored selection follows the stock polygon constraint across meshes.
        mesh,parent=setup("_R")
        c.select(clear=True);left=c.joint(name="Parent_L",position=(0,2,0))
        c.parent(left,"DeformationSystem");c.setAttr(left+".rotate",15,10,5,type="float3")
        other=c.duplicate(mesh,name="LeftMesh")[0]
        c.xform(other,worldSpace=True,translation=(3,6,0))
        c.select(mesh,replace=True)
        plans=CreateSquashController(MayaSquashControllerHost()).apply("Detail",mirror=True)
        assert len(plans)==2 and plans[1].side=="_L"
        assert all("LeftMesh.vtx[" in v for v in plans[1].vertices),plans[1].vertices
        DeleteSquashController(MayaSquashControllerHost()).apply("Detail_R")
        assert not c.objExists("DetailAttach_R") and not c.objExists("DetailAttach_L")
        c.undo();assert c.objExists("DetailAttach_R") and c.objExists("DetailAttach_L")
        c.redo();assert not c.objExists("DetailAttach_R") and not c.objExists("DetailAttach_L")
        report["cases"]["mirror"]={"selected_vertices":len(plans[1].vertices),"delete_undo_redo":True}
        report["status"]="passed"
    except Exception:
        report["status"]="failed";report["traceback"]=traceback.format_exc()
    finally:
        (OUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2),flush=True)
        completion=os.environ.get("ADV_TEST_COMPLETION_FILE")
        if completion:
            Path(completion).write_text(json.dumps({"pid":os.getpid(),"status":report["status"]}),encoding="utf-8")
        if standalone:maya.standalone.uninitialize()
        elif quit_on_finish:c.evalDeferred("quit -force")
    return 0 if report["status"]=="passed" else 1

if __name__=="__main__":raise SystemExit(main())
