"""Real Maya acceptance for the Body / Deform DeltaMush Apply entry."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(report: Path) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        mesh = cmds.polyPlane(name="BodyMesh", width=4., height=4.,
                              subdivisionsX=4, subdivisionsY=4)[0]
        other = cmds.polyCube(name="UnskinnedMesh")[0]
        cmds.select(clear=True)
        root = cmds.joint(name="Root_M", position=(-2., 0., 0.))
        tip = cmds.joint(name="Tip_M", position=(2., 0., 0.))
        cmds.select(clear=True)
        skin = cmds.skinCluster(root, tip, mesh, name="BodySkin",
                                toSelectedBones=True,
                                maximumInfluences=2)[0]
        cmds.createNode("transform", name="Main")
        cmds.createNode("multiplyDivide", name="MainScaleMultiplyDivide")
        count = cmds.polyEvaluate(mesh, vertex=True)
        for index in range(count):
            vertex = f"{mesh}.vtx[{index}]"
            x = cmds.xform(vertex, query=True, objectSpace=True,
                           translation=True)[0]
            fraction = max(0., min(1., (x + 2.) / 4.))
            cmds.skinPercent(skin, vertex, transformValue=(
                (root, 1. - fraction), (tip, fraction)))
        cmds.setAttr(tip + ".rotateY", 65.)

        controller = MayaPanelController()
        cmds.select((mesh, other), replace=True)
        selection = tuple(cmds.ls(selection=True, long=True) or ())
        invalid_rejected = False
        try:
            controller.delta_mush_apply()
        except ValueError as exc:
            invalid_rejected = "SkinCluster" in str(exc)
        preflight_clean = (not cmds.objExists("AdvPy_DeltaMush_BodyMesh")
                           and selection == tuple(cmds.ls(
                               selection=True, long=True) or ()))

        second = cmds.polyCube(name="SecondMesh")[0]
        cmds.skinCluster(root, tip, second, name="SecondSkin",
                         toSelectedBones=True, maximumInfluences=2)
        cmds.select((mesh, second), replace=True)
        multi_count = controller.delta_mush_apply()
        multi_created = (multi_count == 2
            and cmds.objExists("AdvPy_DeltaMush_BodyMesh")
            and cmds.objExists("AdvPy_DeltaMush_SecondMesh"))
        cmds.undo()
        multi_undone = (not cmds.objExists("AdvPy_DeltaMush_BodyMesh")
            and not cmds.objExists("AdvPy_DeltaMush_SecondMesh")
            and cmds.objExists(skin) and cmds.objExists("SecondSkin"))

        cmds.select(mesh, replace=True)
        selection = tuple(cmds.ls(selection=True, long=True) or ())
        vertices = [f"{mesh}.vtx[{index}]" for index in range(count)]
        def positions():
            return tuple(tuple(cmds.pointPosition(vertex, world=True))
                         for vertex in vertices)

        before = positions()
        created = controller.delta_mush_apply()
        deformer = "AdvPy_DeltaMush_BodyMesh"
        after = positions()
        shape = cmds.listRelatives(mesh, shapes=True,
                                   noIntermediate=True, fullPath=True)[0]
        history = cmds.listHistory(shape, pruneDagObjects=True) or []
        maximum_delta = max(abs(a - b) for first, second in zip(before, after)
                            for a, b in zip(first, second))
        valid = (created == 1 and cmds.nodeType(deformer) == "deltaMush"
                 and history.index(deformer) < history.index(skin)
                 and cmds.getAttr(deformer + ".smoothingIterations") == 10
                 and abs(cmds.getAttr(deformer + ".smoothingStep") - .5) < 1e-8
                 and cmds.getAttr(deformer + ".pinBorderVertices")
                 and cmds.getAttr(deformer + ".envelope") == 1.
                 and all(cmds.isConnected(
                     "MainScaleMultiplyDivide.output" + axis,
                     deformer + ".s" + axis.lower()) for axis in "XYZ")
                 and maximum_delta > 1e-5
                 and tuple(cmds.ls(selection=True, long=True) or ()) == selection)

        cmds.undo()
        undone = (not cmds.objExists(deformer)
                  and max(abs(a - b) for first, second in zip(
                      before, positions()) for a, b in zip(first, second))
                  < 1e-5)
        cmds.redo()
        redone = (cmds.objExists(deformer)
                  and max(abs(a - b) for first, second in zip(
                      after, positions()) for a, b in zip(first, second))
                  < 1e-5)
        duplicate_rejected = False
        cmds.select(mesh, replace=True)
        try:
            controller.delta_mush_apply()
        except ValueError as exc:
            duplicate_rejected = "已有 Delta Mush" in str(exc)
        with tempfile.TemporaryDirectory(
                prefix="adv-py-delta-mush-",
                dir=report.parent.resolve()) as folder:
            scene = Path(folder) / "delta-mush.ma"
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(scene), open=True, force=True)
            reopened = (cmds.objExists(deformer)
                and cmds.nodeType(deformer) == "deltaMush"
                and max(abs(a - b) for first, second in zip(
                    after, positions()) for a, b in zip(first, second))
                < 1e-5)
            vertex = f"{mesh}.vtx[12]"
            weights_before = tuple(cmds.skinPercent(
                skin, vertex, query=True, value=True))
            cmds.select((mesh, other), replace=True)
            harden_invalid = False
            try:
                controller.delta_mush_harden_weights()
            except ValueError as exc:
                harden_invalid = "SkinCluster" in str(exc)
            harden_preflight = (harden_invalid and tuple(cmds.skinPercent(
                skin, vertex, query=True, value=True)) == weights_before)
            cmds.select((mesh, second), replace=True)
            hardened_count = controller.delta_mush_harden_weights()
            weights_hardened = tuple(cmds.skinPercent(
                skin, vertex, query=True, value=True))
            harden_result = (hardened_count == 2 and
                sum(value == 1. for value in weights_hardened) == 1 and
                sum(value == 0. for value in weights_hardened) == len(weights_hardened) - 1)
            cmds.undo()
            harden_undone = tuple(cmds.skinPercent(
                skin, vertex, query=True, value=True)) == weights_before
            cmds.redo()
            harden_redone = tuple(cmds.skinPercent(
                skin, vertex, query=True, value=True)) == weights_hardened
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(scene), open=True, force=True)
            harden_reopened = tuple(cmds.skinPercent(
                skin, vertex, query=True, value=True)) == weights_hardened
        checks = {
            "mixed_selection_rejected_before_write":
                invalid_rejected and preflight_clean,
            "multi_mesh_single_undo": multi_created and multi_undone,
            "post_skin_deformer_changes_pose": valid,
            "single_undo_redo": undone and redone,
            "duplicate_rejected": duplicate_rejected,
            "save_reopen": reopened,
            "harden_mixed_selection_preflight": harden_preflight,
            "harden_two_meshes_single_undo_redo":
                harden_result and harden_undone and harden_redone,
            "harden_save_reopen": harden_reopened,
        }
        report.write_text(json.dumps({
            **checks, "maximum_delta_cm": maximum_delta,
            "status": "passed" if all(checks.values()) else "failed",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
