"""Migrate direct original FK keys without changing curve or mesh motion."""
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _points(mesh: str):
    from maya.api import OpenMaya as om
    selection = om.MSelectionList()
    selection.add(mesh)
    dag = selection.getDagPath(0)
    if dag.apiType() == om.MFn.kTransform:
        dag.extendToShape()
    return tuple(tuple(float(value) for value in point)
                 for point in om.MFnMesh(dag).getPoints(om.MSpace.kWorld))


def _curve(cmds, plug: str):
    source = cmds.listConnections(plug, source=True,
        destination=False, skipConversionNodes=True) or []
    if len(source) != 1:
        raise AssertionError("动画通道曲线缺失：" + plug)
    node = source[0]
    return {
        "type": cmds.nodeType(node),
        "times": cmds.keyframe(node, query=True, timeChange=True) or [],
        "values": cmds.keyframe(node, query=True, valueChange=True) or [],
        "in_tangent": cmds.keyTangent(node, query=True,
                                      inTangentType=True) or [],
        "out_tangent": cmds.keyTangent(node, query=True,
                                       outTangentType=True) or [],
        "in_angle": cmds.keyTangent(node, query=True, inAngle=True) or [],
        "out_angle": cmds.keyTangent(node, query=True, outAngle=True) or [],
        "in_weight": cmds.keyTangent(node, query=True, inWeight=True) or [],
        "out_weight": cmds.keyTangent(node, query=True, outWeight=True) or [],
        "weighted": cmds.keyTangent(node, query=True,
                                     weightedTangents=True) or [],
        "pre_infinity": cmds.getAttr(node + ".preInfinity"),
        "post_infinity": cmds.getAttr(node + ".postInfinity"),
    }


def main(scene: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.application.character_registry import ResolveBodyCharacter
        from adv_py.product.maya_panel_controller import MayaPanelController

        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        cmds.undoInfo(state=True)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        cmds.currentTime(1, edit=True)
        skin = (cmds.ls(type="skinCluster") or [])[0]
        shape = (cmds.skinCluster(skin, query=True, geometry=True) or [])[0]
        mesh = (cmds.listRelatives(shape, parent=True,
                                   fullPath=True) or [])[0]
        controller = MayaPanelController()

        for time, value in ((1, 0.0), (5, 10.0)):
            cmds.setKeyframe("FKCup_R.rotateX", time=time, value=value)
        try:
            controller.original_skin_migrate(":", skin)
        except ValueError as error:
            unmapped_rejected = ("尚无新 Rig 对应入口" in str(error)
                and cmds.objExists(skin)
                and not cmds.objExists("AdvPy_MigratedSkin"))
        else:
            unmapped_rejected = False
        cmds.cutKey("FKCup_R.rotateX", clear=True)
        if not unmapped_rejected:
            raise AssertionError("未知带键控制器未在替换前拒绝")

        pairs = (
            ("FKRoot_M.rotateY", "AdvPy_TorsoRoot_MFK.rotateY", 15.0),
            ("FKElbow_R.rotateZ", "AdvPy_ElbowFK_R.rotateZ", 65.0),
            ("FKHip_R.rotateY", "AdvPy_HipFK_R.rotateY", 22.0),
        )
        for source, _, peak in pairs:
            for time, value in ((1, 0.0), (5, peak), (9, 0.0)):
                cmds.setKeyframe(source, time=time, value=value)
            cmds.keyTangent(source, edit=True, time=(5, 5),
                            inTangentType="flat", outTangentType="flat")
        cmds.keyTangent("FKRoot_M.rotateY", edit=True,
                        weightedTangents=True)
        cmds.keyTangent("FKRoot_M.rotateY", edit=True, time=(5, 5),
                        inTangentType="fixed", outTangentType="fixed",
                        inAngle=25.0, outAngle=-25.0,
                        inWeight=2.0, outWeight=2.0)
        before_curves = {target: _curve(cmds, source)
                         for source, target, _ in pairs}
        sample_frames = (1, 3, 5, 7, 9)
        source_points = {}
        for frame in sample_frames:
            cmds.currentTime(frame, edit=True)
            source_points[frame] = _points(mesh)
        cmds.currentTime(1, edit=True)

        result = controller.original_skin_migrate(":", skin)
        after_curves = {target: _curve(cmds, target)
                        for _, target, _ in pairs}
        curves_equal = before_curves == after_curves
        body_count = len(ResolveBodyCharacter(
            MayaBodyBuildHost()).execute().body)
        cmds.undo()
        undo_restored = (not cmds.objExists(result.skin)
            and cmds.objExists(skin)
            and all(_curve(cmds, source) == before_curves[target]
                for source, target, _ in pairs))
        cmds.redo()
        redo_restored = all(_curve(cmds, target) == before_curves[target]
            for _, target, _ in pairs)
        pose_errors = {}
        for frame in sample_frames:
            cmds.currentTime(frame, edit=True)
            pose_errors[str(frame)] = max(abs(a - b)
                for source, target in zip(source_points[frame],
                    _points(result.mesh)) for a, b in zip(source, target))
        cmds.currentTime(1, edit=True)
        saved = report.with_suffix(".mb").resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(rename=str(saved))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(saved), open=True, force=True,
                  executeScriptNodes=False)
        reopen_restored = all(_curve(cmds, target)
            == before_curves[target] for _, target, _ in pairs)
        data = {"source": scene.name,
                "unmapped_keys_rejected": unmapped_rejected,
                "copied_curves": result.animation_curves,
                "curves_equal": curves_equal,
                "body_count": body_count,
                "undo_restored": undo_restored,
                "redo_restored": redo_restored,
                "reopen_restored": reopen_restored,
                "pose_world_point_errors": pose_errors,
                "saved_scene": saved.name}
        report.write_text(json.dumps(data, indent=2) + "\n",
                          encoding="utf-8")
        if not (unmapped_rejected and curves_equal and undo_restored
                and redo_restored and reopen_restored
                and result.animation_curves == len(pairs)
                and body_count == 74
                and max(pose_errors.values()) <= 1e-5):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
