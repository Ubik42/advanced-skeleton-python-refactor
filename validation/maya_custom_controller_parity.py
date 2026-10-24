"""Compare unmodified ADV conversion against Python in one graphical Maya.

Only the option dialog callback is supplied by the fixture. The conversion,
pose mapping, weight procedures, constraints and native deformers are ADV.
"""
from pathlib import Path
import json
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "validation/results/custom-controller-current"
POSES = ({}, {"translateX": .4}, {"translateY": .5, "translateZ": -.2},
         {"rotateX": 25.}, {"rotateY": 15., "rotateZ": -10.},
         {"scaleX": 1.15, "scaleY": .9}, {"parentTranslate": .5},
         {"parentRotate": 20., "translateY": .3})


def setup(face=False):
    from maya import cmds as c
    c.file(new=True, force=True)
    c.undoInfo(state=True)
    c.optionVar(intValue=("deformationUseComponentTags", 0))
    for name in ("MotionSystem", "DeformationSystem", "Main", "buildPose"):
        c.createNode("transform", name=name)
    c.addAttr("buildPose", longName="udAttr", dataType="string")
    c.setAttr("buildPose.udAttr", "", type="string")
    for name in ("ControlSet", "DeformSet"):
        c.sets(empty=True, name=name)
    c.sets("Main", add="ControlSet")
    if face:
        for name in ("FaceMotionSystem", "faceBuildPose", "ctrlBox", "FaceFitSkeleton"):
            c.createNode("transform", name=name)
        c.addAttr("faceBuildPose", longName="udAttr", dataType="string")
        c.setAttr("faceBuildPose.udAttr", "", type="string")
        c.addAttr("ctrlBox", longName="CustomCtrlVis", attributeType="bool", defaultValue=True)
        c.addAttr("FaceFitSkeleton", longName="HeadJoint", dataType="string")
        c.setAttr("FaceFitSkeleton.HeadJoint", "Parent_R", type="string")
        for name in ("FaceControlSet", "FaceAllSet"):
            c.sets(empty=True, name=name)
    c.select(clear=True)
    parent = c.joint(name="Parent_R", position=(-3, 2, 0))
    c.parent(parent, "DeformationSystem")
    c.setAttr(parent + ".rotate", 15, 10, 5, type="float3")
    c.select(clear=True)
    left = c.joint(name="Parent_L", position=(3, 2, 0))
    c.parent(left, "DeformationSystem")
    c.setAttr(left + ".rotate", 15, 10, 5, type="float3")
    c.sets([parent, left], add="DeformSet")
    mesh = c.polyCube(name="Mesh", width=10, height=4, depth=2,
                      subdivisionsX=12, subdivisionsY=6, subdivisionsZ=4)[0]
    c.xform(mesh, worldSpace=True, translation=(0, 5, 0))
    c.skinCluster(parent, left, mesh, toSelectedBones=True, maximumInfluences=3,
                  dropoffRate=4, removeUnusedInfluence=False, name="MeshSC")
    source, handle = c.softMod(mesh, name="sourceSoftMod", falloffCenter=(-3, 5, 0),
                               falloffRadius=2.5, falloffMode=0,
                               falloffAroundSelection=False)
    c.select(handle, replace=True)
    return source


def native_options(kind, local, mirror, layered=False):
    from maya import mel
    values = {"type": kind, "name": "Detail", "parent": "Parent_R",
              "skinCluster": "*new" if layered else "MeshSC"}
    body = ['setAttr -type "string" CreatingCustomControl.%s %s;' %
            (attr, json.dumps(value)) for attr, value in values.items()]
    body += ['setAttr CreatingCustomControl.%s %d;' % (attr, int(value))
             for attr, value in {"mirror": mirror, "middle": False,
                                  "local": local, "partialParent": False}.items()]
    # A modal layout processes Qt timers during startup; MEL evalDeferred waits
    # for the startup command to return and would leave this fixture modal open.
    dismiss = "from PySide2.QtCore import QTimer; from maya import cmds; QTimer.singleShot(0, lambda: cmds.layoutDialog(dismiss='OK'))"
    body += ['python(%s);' % json.dumps(dismiss)]
    mel.eval("global proc asCCLayout(){" + "".join(body) + "}")


def snapshot(mirror=False):
    from maya import cmds as c
    sides = ("_R", "_L") if mirror else ("_R",)
    meshes = ["Mesh"] + (["MeshOther"] if c.objExists("MeshOther") else [])
    return {"vertices": [value for mesh in meshes for value in c.xform(
                         mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)],
            "controls": [c.xform("Detail" + side, query=True, worldSpace=True, matrix=True)
                         for side in sides]}


def samples(mirror=False):
    from maya import cmds as c
    rows = []
    sides = ("_R", "_L") if mirror else ("_R",)
    for pose in POSES:
        for side in sides:
            control = "Detail" + side
            for attr, neutral in (("translate", 0.), ("rotate", 0.), ("scale", 1.)):
                for axis in "XYZ":
                    c.setAttr(control + "." + attr + axis, pose.get(attr + axis, neutral))
            c.setAttr("Parent" + side + ".translateX", (-3 if side == "_R" else 3)
                      + pose.get("parentTranslate", 0.))
            c.setAttr("Parent" + side + ".rotateZ", 5 + pose.get("parentRotate", 0.))
        rows.append(snapshot(mirror))
    return rows


def extra_mesh():
    from maya import cmds as c
    mesh = c.polyCube(name="MeshOther", width=2, height=2, depth=2,
                      subdivisionsX=3, subdivisionsY=3, subdivisionsZ=3)[0]
    c.xform(mesh, worldSpace=True, translation=(-3, 5, 0))
    return mesh


def max_error(expected, actual):
    def flatten(value):
        for item in value:
            if isinstance(item, list):
                yield from flatten(item)
            else:
                yield float(item)
    errors = []
    for left, right in zip(expected, actual):
        row = {}
        for key in left:
            a, b = list(flatten(left[key])), list(flatten(right[key]))
            assert len(a) == len(b), (key, len(a), len(b))
            row[key] = max((abs(x-y) for x, y in zip(a, b)), default=0.)
        errors.append(row)
    return max(value for row in errors for value in row.values()), errors


def main(*, standalone=False, quit_on_finish=False):
    if standalone:
        import maya.standalone
        maya.standalone.initialize(name="python")
    from maya import cmds as c, mel
    from adv_py.adapters.maya_custom_controller import MayaCustomControllerHost
    from adv_py.application.custom_controller import (
        BuildCustomController, DeleteCustomController, ExtendSoftModController,
        MirrorClusterControlWeights)
    from adv_py.core.custom_controller import CustomControlKind
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "cases": {}, "execution": "graphical Maya",
              "reference": "unmodified asConvertSoftModToCustomControl; fixture supplies option dialog"}
    face = os.environ.get("ADV_CUSTOM_SCOPE") == "face"
    report["scope"] = "face" if face else "body"
    try:
        mel.eval('source "' + (ROOT / "local/adv_6_925/AdvancedSkeleton.mel").as_posix() + '";')
        mel.eval('global string $gSelect="selectSuperContext"; global string $gMove="moveSuperContext";')
        option_window = c.window(visible=False)
        c.columnLayout()
        c.checkBox("asBodyOffsetParentMatrixCheckBox", value=False)
        for kind in (CustomControlKind.SOFT_MOD, CustomControlKind.CLUSTER, CustomControlKind.SKIN):
            source_kind = {CustomControlKind.SOFT_MOD: "SoftMod", CustomControlKind.CLUSTER: "Cluster",
                           CustomControlKind.SKIN: "Skin"}[kind]
            modes = [(True, False, False), (False, False, False), (True, True, False)]
            if kind is CustomControlKind.SKIN and not face:
                modes.append((True, False, True))
            for local, mirror, layered in modes:
                case = "%s-local%s-mirror%s-layered%s" % (kind.value, int(local), int(mirror), int(layered))
                report["active_case"] = case
                setup(face); native_options(source_kind, local, mirror, layered)
                mel.eval('asConvertSoftModToCustomControl "%s" %d;' % (source_kind, int(face)))
                expected = samples(mirror)
                if kind is CustomControlKind.CLUSTER and mirror:
                    c.select("Detail_R", replace=True)
                    mel.eval("asMirrorClusterControlWeights;")
                    expected = samples(mirror)
                extra = extra_mesh()
                c.select("Detail_R", extra, replace=True)
                mel.eval("asAddSoftModInfluencedObject;")
                expected = samples(mirror)
                native_state = MayaCustomControllerHost(face=face).capture_custom_control("Detail_R")
                assert native_state.kind is kind and native_state.weighted_vertex_count > 0
                assert set(native_state.influenced_meshes) == {"|Mesh", "|MeshOther"}
                DeleteCustomController(MayaCustomControllerHost(face=face)).apply("Detail_R")
                assert not c.objExists("Detail_R")
                c.undo(); assert max_error([expected[-1]], [snapshot(mirror)])[0] < 1e-4
                source = setup(face)
                result = BuildCustomController(MayaCustomControllerHost(face=face)).apply(
                    source, kind, "Detail", parent_joint="Parent_R", local=local,
                    mirror=mirror, skin_cluster="*new" if layered else None)
                samples(mirror)
                if kind is CustomControlKind.CLUSTER and mirror:
                    MirrorClusterControlWeights(MayaCustomControllerHost(face=face)).apply("Detail_R")
                    samples(mirror)
                extra = extra_mesh()
                ExtendSoftModController(MayaCustomControllerHost(face=face)).apply("Detail_R", extra)
                maximum, errors = max_error(expected, samples(mirror))
                assert maximum < 1e-4, (case, maximum, errors)
                scene = OUT / (("face-" if face else "") + case + ".mb")
                c.file(rename=str(scene)); c.file(save=True, type="mayaBinary", force=True)
                c.file(str(scene), open=True, force=True)
                prior = snapshot(mirror)
                DeleteCustomController(MayaCustomControllerHost(face=face)).apply("Detail_R")
                assert not c.objExists("Detail_R") and (not mirror or not c.objExists("Detail_L"))
                c.undo(); assert max_error([prior], [snapshot(mirror)])[0] < 1e-4
                c.redo(); assert not c.objExists("Detail_R")
                report["cases"][case] = {"maximum_error": maximum, "errors": errors,
                                          "save_reopen_delete_undo_redo": True,
                                          "stock_control_capture_delete_undo": True,
                                          "extend_mesh_parity": True,
                                          "cluster_mirror_weights_parity": kind is CustomControlKind.CLUSTER and mirror}
        report["status"] = "passed"
        report.pop("active_case", None)
    except Exception:
        report["status"] = "failed"
        report["traceback"] = traceback.format_exc()
    finally:
        (OUT / ("face-report.json" if face else "report.json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        completion = os.environ.get("ADV_TEST_COMPLETION_FILE")
        if completion:
            Path(completion).write_text(json.dumps({"pid": os.getpid(), "status": report["status"]}), encoding="utf-8")
        if standalone:
            maya.standalone.uninitialize()
        elif quit_on_finish:
            c.evalDeferred("quit -force")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
