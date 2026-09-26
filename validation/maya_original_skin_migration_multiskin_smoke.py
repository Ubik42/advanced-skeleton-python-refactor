"""Preserve an unrelated referenced Skin while migrating the public rig."""
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(scene: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        extra_file = report.with_name("maya2024-extra-referenced-skin.ma")
        cmds.file(new=True, force=True)
        cube = cmds.polyCube(name="ExtraMesh")[0]
        cmds.select(clear=True)
        joint = cmds.joint(name="ExtraJoint", position=(0, 0, 0))
        cmds.skinCluster(joint, cube, name="ExtraSkin")
        cmds.file(rename=str(extra_file.resolve()))
        cmds.file(save=True, type="mayaAscii", force=True)

        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        source_skin = (cmds.ls(type="skinCluster") or [])[0]
        original = MayaDenseSkinHost().capture_dense_skin(source_skin)
        cmds.file(str(extra_file.resolve()), reference=True,
                  namespace="prop", returnNewNodes=False)
        extra_skin = (cmds.ls("prop:ExtraSkin", type="skinCluster") or [])[0]
        extra_before = MayaDenseSkinHost().capture_dense_skin(extra_skin)
        references_before = tuple(cmds.file(query=True, reference=True) or ())
        controller = MayaPanelController()
        fit_parent = (cmds.listRelatives("FitSkeleton", parent=True,
                                        fullPath=True) or [])[0]
        cmds.parent("prop:ExtraMesh", fit_parent)
        try:
            controller.original_skin_migrate(":", source_skin)
        except ValueError as error:
            referenced_child_rejected = ("引用节点" in str(error)
                and MayaDenseSkinHost().capture_dense_skin(source_skin)
                    == original and not cmds.objExists("AdvPy_MigratedMesh"))
        else:
            referenced_child_rejected = False
        cmds.undo()
        if not referenced_child_rejected:
            raise AssertionError("角色容器内的引用资产未在替换前拒绝")
        try:
            controller.original_skin_migrate(":")
        except ValueError:
            ambiguous_rejected = (
                MayaDenseSkinHost().capture_dense_skin(source_skin) == original
                and MayaDenseSkinHost().capture_dense_skin(extra_skin)
                    == extra_before
                and not cmds.objExists("AdvPy_MigratedMesh"))
        else:
            ambiguous_rejected = False
        if not ambiguous_rejected:
            raise AssertionError("多个 Skin 时应先要求明确选择来源")

        result = controller.original_skin_migrate(":", source_skin)
        target_after = MayaDenseSkinHost().capture_dense_skin(result.skin)
        extra_after = MayaDenseSkinHost().capture_dense_skin(extra_skin)
        references_after = tuple(cmds.file(query=True, reference=True) or ())
        untouched = (extra_after == extra_before
            and references_after == references_before
            and cmds.referenceQuery(extra_skin, isNodeReferenced=True))
        cmds.undo()
        undo_restored = (not cmds.objExists(result.skin)
            and MayaDenseSkinHost().capture_dense_skin(source_skin) == original
            and MayaDenseSkinHost().capture_dense_skin(extra_skin)
                == extra_before)
        cmds.redo()
        redo_restored = (MayaDenseSkinHost().capture_dense_skin(result.skin)
            == target_after and MayaDenseSkinHost().capture_dense_skin(
                extra_skin) == extra_before)
        saved = report.with_suffix(".mb").resolve()
        cmds.file(rename=str(saved))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(saved), open=True, force=True,
                  executeScriptNodes=False)
        reopen_restored = (MayaDenseSkinHost().capture_dense_skin(result.skin)
            == target_after and MayaDenseSkinHost().capture_dense_skin(
                extra_skin) == extra_before
            and cmds.referenceQuery(extra_skin, isNodeReferenced=True))
        data = {"source": scene.name,
                "referenced_child_rejected": referenced_child_rejected,
                "ambiguous_source_rejected": ambiguous_rejected,
                "extra_reference_untouched": untouched,
                "target_vertices": result.vertices,
                "target_influences": result.influences,
                "undo_restored": undo_restored,
                "redo_restored": redo_restored,
                "reopen_restored": reopen_restored,
                "saved_scene": saved.name}
        report.write_text(json.dumps(data, indent=2) + "\n",
                          encoding="utf-8")
        if not (untouched and undo_restored and redo_restored
                and reopen_restored and result.vertices == 18151
                and result.influences == 121):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
