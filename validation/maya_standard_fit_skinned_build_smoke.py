"""Build a skinned character directly from the public Fit in one action."""
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, report: Path, *, prepare_only: bool = False) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.application.external_fit_export import ExportExternalFitSkeleton
        from adv_py.application.fit_skeleton_io import CreateAndImportFitSkeleton
        from adv_py.application.registered_skinned_body_build import (
            BuildRegisteredSkinnedBodyCharacter)
        from adv_py.application.character_registry import ResolveBodyCharacter
        from adv_py.product.maya_panel_controller import MayaPanelController

        def point(mesh):
            return tuple(cmds.pointPosition(mesh + ".vtx[0]",
                                            world=True))

        report.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="advpy-fit-skin-") as temp:
            temp = Path(temp)
            cmds.file(str(scene.resolve()), open=True, force=True,
                      executeScriptNodes=False)
            fit_document = temp / "public.fit.json"
            ExportExternalFitSkeleton(MayaBodyBuildHost()).apply(fit_document)
            source_skin = (cmds.ls(type="skinCluster") or [])[0]
            shape = (cmds.skinCluster(source_skin, query=True,
                                      geometry=True) or [])[0]
            source_mesh = (cmds.listRelatives(shape, parent=True,
                                               fullPath=True) or [])[0]
            mesh = cmds.duplicate(source_mesh,
                                  returnRootsOnly=True)[0]
            mesh = cmds.parent(mesh, world=True)[0] if cmds.listRelatives(
                mesh, parent=True) else mesh
            mesh = cmds.rename(mesh, "BodyMesh")
            cmds.delete(mesh, constructionHistory=True)
            cmds.select(mesh, replace=True)
            mesh_file = temp / "body.mb"
            cmds.file(str(mesh_file), exportSelected=True,
                      type="mayaBinary", force=True)

            cmds.file(new=True, force=True)
            cmds.file(str(mesh_file), i=True, type="mayaBinary",
                      executeScriptNodes=False)
            cmds.polyCube(name="GarmentMesh", width=12, height=8, depth=5)
            CreateAndImportFitSkeleton(MayaBodyBuildHost()).apply(fit_document)
            meshes = tuple((cmds.ls(name, long=True,
                                    type="transform") or [])[0]
                           for name in ("BodyMesh", "GarmentMesh"))
            original_points = tuple(point(mesh) for mesh in meshes)
            cmds.undoInfo(state=True)
            if prepare_only:
                prepared = report.resolve()
                cmds.file(rename=str(prepared))
                cmds.file(save=True, type="mayaBinary", force=True)
                return 0

            def fault(stage):
                if stage == "skins-bound":
                    raise RuntimeError("injected skinned build fault")
            try:
                BuildRegisteredSkinnedBodyCharacter(
                    MayaBodyBuildHost()).apply(meshes,
                        infer_missing_labels=True, on_stage=fault)
            except RuntimeError as error:
                rolled_back = (str(error) == "injected skinned build fault"
                    and not cmds.objExists("Root_M")
                    and not (cmds.ls(type="skinCluster") or [])
                    and tuple(point(mesh) for mesh in meshes)
                        == original_points)
            else:
                rolled_back = False
            if not rolled_back:
                raise AssertionError("标准 Fit 蒙皮构建未整体回滚")

            built = MayaPanelController().body_build(":", meshes=meshes,
                infer_missing_labels=True)
            skins = tuple(sorted(cmds.ls(type="skinCluster") or []))
            influences = tuple(len(cmds.skinCluster(skin, query=True,
                influence=True) or []) for skin in skins)
            body_joints = len(ResolveBodyCharacter(
                MayaBodyBuildHost()).execute().body)
            cmds.setAttr("AdvPy_Global.translateX", 2)
            posed = tuple(point(mesh) for mesh in meshes)
            moved = all(abs(a[0] - b[0]) > 1.9 for a, b in
                        zip(posed, original_points))
            cmds.setAttr("AdvPy_Global.translateX", 0)
            cmds.undo()
            cmds.undo()
            cmds.undo()
            undo_restored = (not cmds.objExists("Root_M")
                             and not (cmds.ls(type="skinCluster") or []))
            cmds.redo()
            redo_restored = (len(cmds.ls(type="skinCluster") or []) == 2
                             and cmds.objExists("Root_M"))
            saved = (temp / "standard-fit-skinned.mb").resolve()
            cmds.file(rename=str(saved))
            cmds.file(save=True, type="mayaBinary", force=True)
            cmds.file(str(saved), open=True, force=True,
                      executeScriptNodes=False)
            reopen_restored = (len(cmds.ls(type="skinCluster") or []) == 2
                and len(ResolveBodyCharacter(
                    MayaBodyBuildHost()).execute().body) == 74)

            cmds.file(new=True, force=True)
            cmds.namespace(add="Hero")
            cmds.file(str(mesh_file), i=True, type="mayaBinary",
                      executeScriptNodes=False)
            cmds.rename("BodyMesh", "Hero:BodyMesh")
            cmds.polyCube(name="Hero:GarmentMesh", width=12,
                          height=8, depth=5)
            CreateAndImportFitSkeleton(MayaBodyBuildHost(
                namespace="Hero")).apply(fit_document)
            namespaced_meshes = tuple((cmds.ls("Hero:" + name,
                long=True, type="transform") or [])[0]
                for name in ("BodyMesh", "GarmentMesh"))
            namespaced = MayaPanelController().body_build("Hero",
                meshes=namespaced_meshes, infer_missing_labels=True)
            namespaced_skins = tuple(sorted(cmds.ls("Hero:*",
                type="skinCluster") or []))
            namespaced_built = (namespaced.joint_count == 74
                and namespaced_skins == ("Hero:AdvPy_BodySkin",
                                     "Hero:AdvPy_BodySkin_2"))
            data = {"source": scene.name, "meshes": len(meshes),
                    "skins": skins, "influences": influences,
                    "body_joints": body_joints,
                    "channels": built.channel_count,
                    "fault_rolled_back": rolled_back,
                    "global_moved_both": moved,
                    "undo_restored": undo_restored,
                    "redo_restored": redo_restored,
                    "reopen_restored": reopen_restored,
                    "namespaced_built": namespaced_built}
            report.write_text(json.dumps(data, indent=2) + "\n",
                              encoding="utf-8")
            if not (len(skins) == 2 and body_joints == 74
                    and built.channel_count > 200 and moved
                    and undo_restored and redo_restored
                    and reopen_restored and namespaced_built):
                raise AssertionError(data)
            return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          prepare_only="--prepare" in sys.argv[3:]))
