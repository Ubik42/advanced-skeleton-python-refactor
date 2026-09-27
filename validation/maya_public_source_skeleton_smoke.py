"""Build a new skinned character from the public Sam Fit and static body."""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(source: Path, output: Path, *, prepare_only: bool = False) -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    from maya import cmds
    from adv_py.product.maya_panel_controller import MayaPanelController

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="advpy-public-source-") as temp:
        cmds.file(str(source.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        root = (cmds.ls("Root", long=True, type="joint") or [])[0]
        skin = (cmds.ls(type="skinCluster") or [])[0]
        shape = (cmds.skinCluster(skin, query=True, geometry=True) or [])[0]
        original_mesh = (cmds.listRelatives(shape, parent=True,
                                            fullPath=True) or [])[0]
        mesh = cmds.duplicate(original_mesh, returnRootsOnly=True)[0]
        if cmds.listRelatives(mesh, parent=True):
            mesh = cmds.parent(mesh, world=True)[0]
        mesh = cmds.rename(mesh, "SourceBodyMesh")
        cmds.delete(mesh, constructionHistory=True)
        vertices = int(cmds.polyEvaluate(mesh, vertex=True))
        cmds.select(root, mesh, replace=True)
        extraction = Path(temp) / "source.mb"
        cmds.file(str(extraction), exportSelected=True,
                  type="mayaBinary", force=True)
        if prepare_only:
            prepared = output / "public-source-input.mb"
            shutil.copyfile(extraction, prepared)
            print("PREPARED public source", prepared, vertices)
            return

        cmds.file(new=True, force=True)
        cmds.file(str(extraction), i=True, type="mayaBinary",
                  executeScriptNodes=False)
        root = (cmds.ls("Root", long=True, type="joint") or [])[0]
        mesh = (cmds.ls("SourceBodyMesh", long=True,
                        type="transform") or [])[0]
        result = MayaPanelController().body_build_from_source(
            ":", root, meshes=(mesh,), segment_influences=True)
        skins = cmds.ls("AdvPy:*", type="skinCluster") or []
        assert result.namespace == "AdvPy" and result.joint_count == 70
        assert len(skins) == 1
        assert cmds.objExists("Root") and cmds.objExists("SourceBodyMesh")
        assert int(cmds.polyEvaluate("AdvPy:SourceBodyMesh",
                                     vertex=True)) == vertices

        cmds.setKeyframe("AdvPy:AdvPy_Global", attribute="translateX",
                         time=1, value=0)
        cmds.setKeyframe("AdvPy:AdvPy_Global", attribute="translateX",
                         time=5, value=2)
        fbx = (output / "public-source.fbx").resolve()
        publication = MayaPanelController().publish_fbx(
            "AdvPy", fbx, start=1, end=5, include_skins=True)
        saved = (output / "public-source.mb").resolve()
        cmds.file(rename=str(saved))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(saved), open=True, force=True,
                  executeScriptNodes=False)
        reopen_skins = len(cmds.ls("AdvPy:*", type="skinCluster") or [])
        reopen_keys = cmds.keyframe("AdvPy:AdvPy_Global.translateX",
                                    query=True, timeChange=True) or []

        cmds.file(new=True, force=True)
        cmds.loadPlugin("fbxmaya", quiet=True)
        cmds.file(str(fbx), i=True, type="FBX", ignoreVersion=True,
                  executeScriptNodes=False)
        fbx_joints = len(cmds.ls(type="joint") or [])
        fbx_skins = len(cmds.ls(type="skinCluster") or [])
        fbx_meshes = tuple(cmds.ls(type="mesh", noIntermediate=True) or [])
        root_motion = (cmds.ls("RootMotion", type="joint") or [])[0]
        cmds.currentTime(1)
        first = cmds.xform(root_motion, query=True, worldSpace=True,
                           translation=True)[0]
        cmds.currentTime(5)
        last = cmds.xform(root_motion, query=True, worldSpace=True,
                          translation=True)[0]
        report = {
            "source_fit_joints": 41,
            "vertices": vertices,
            "body_joints": result.joint_count,
            "segment_joints": result.segment_joint_count,
            "skins": len(skins),
            "fbx_bytes": publication.bytes_written,
            "reopen_skins": reopen_skins,
            "reopen_keys": reopen_keys,
            "fbx_joints": fbx_joints,
            "fbx_skins": fbx_skins,
            "fbx_mesh_shapes": len(fbx_meshes),
            "root_motion_x": last - first,
        }
        report["passed"] = (vertices == 18151 and reopen_skins == 1
            and reopen_keys == [1.0, 5.0] and fbx_joints >= 71
            and fbx_skins == 1 and len(fbx_meshes) == 1
            and abs(last - first - 2.0) < 1e-4)
        (output / "public-source.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        if not report["passed"]:
            raise AssertionError(report)
        print("PASS public source skeleton", report)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]),
         prepare_only="--prepare" in sys.argv[3:])
