"""Compare Face shell conversion with Maya's native polyConvertToShell.

This invokes the installed Maya command, never an ADV MEL procedure.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(output):
    import maya.standalone
    maya.standalone.initialize(name="python")
    from maya import cmds, mel
    from adv_py.adapters.maya_face_topology import original_face_connected_vertices
    from adv_py.adapters.maya_face_eye_lid_prep import MayaFaceEyeLidPrepMixin

    class Host(MayaFaceEyeLidPrepMixin):
        _cmds = cmds

        def scene_address(self, value):
            return value

    cmds.file(new=True, force=True)
    cmds.namespace(add="FaceActor")
    left = cmds.polyPlane(name="FaceActor:left", subdivisionsX=3,
                          subdivisionsY=3, constructionHistory=False)[0]
    right = cmds.polyPlane(name="FaceActor:right", subdivisionsX=2,
                           subdivisionsY=2, constructionHistory=False)[0]
    cmds.move(3, 0, 0, right)
    mesh = cmds.polyUnite(left, right, name="FaceActor:FaceMesh",
                         constructionHistory=False, mergeUVSets=1)[0]
    parent = cmds.group(mesh, name="FaceActor:Model")
    mesh = cmds.listRelatives(parent, children=True, fullPath=True)[0]
    report = {"status": "running", "cases": []}
    for indices in ((0,), (16,), (0, 16), (1, 5)):
        seeds = [mesh + f".vtx[{i}]" for i in indices]
        cmds.select(seeds, replace=True)
        mel.eval("polyConvertToShell;")
        native = set(cmds.ls(selection=True, long=True, flatten=True) or [])
        constraint = cmds.polySelectConstraint(query=True, stateString=True)
        actual = original_face_connected_vertices(Host(), mesh, seeds)
        assert set(actual) == native, (indices, len(actual), len(native))
        assert cmds.polySelectConstraint(query=True, stateString=True) == constraint
        cmds.select(seeds, replace=True)
        cmds.undoInfo(openChunk=True, chunkName="Face connected shell")
        cmds.select(actual, replace=True)
        cmds.undoInfo(closeChunk=True)
        cmds.undo()
        assert set(cmds.ls(selection=True, long=True, flatten=True)) == set(seeds)
        cmds.redo()
        assert set(cmds.ls(selection=True, long=True, flatten=True)) == native
        report["cases"].append({"seeds": indices, "vertex_count": len(native),
                                "native_equal": True, "undo_redo": True})
    # Exercise the original detached-lid branch, not only connected faces.
    # The copied shell and sampler must disappear again on native redo, while
    # the production mesh, skin and memberships keep their original identity.
    cmds.createNode("transform", name="FaceBuildInProgress")
    cmds.select(clear=True)
    joint = cmds.joint(name="Head_M")
    skin = cmds.skinCluster(joint, mesh, toSelectedBones=True)[0]
    original_points = cmds.xform(mesh + ".vtx[*]", query=True,
                                 worldSpace=True, translation=True)
    original_skin = cmds.ls(skin, uuid=True)[0]
    cmds.undoInfo(openChunk=True, chunkName="Detached EyeLid shell")
    vertex = Host()._original_lid_brow_shell_vertex(
        {"geometry": mesh}, "", (mesh + ".vtx[0]",), mesh + ".vtx[16]")
    cmds.createNode("transform", name="ShellSamplingCompleted")
    cmds.undoInfo(closeChunk=True)
    assert vertex.startswith(mesh + ".vtx[")
    assert not cmds.objExists("asTempSingleShellFace")
    cmds.undo()
    assert not cmds.objExists("ShellSamplingCompleted")
    cmds.redo()
    assert cmds.objExists("ShellSamplingCompleted")
    assert not cmds.objExists("asTempSingleShellFace")
    assert not cmds.objExists("closestSampler")
    assert cmds.ls(skin, uuid=True)[0] == original_skin
    assert cmds.xform(mesh + ".vtx[*]", query=True,
                      worldSpace=True, translation=True) == original_points
    report["detached_lid"] = {"sampled_vertex": vertex, "undo_redo": True,
                               "production_mesh_and_skin_unchanged": True}
    report["status"] = "passed"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
