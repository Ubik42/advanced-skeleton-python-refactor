"""Exercise panel controller source export and cross-scene transfer without UI."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def create_joints(cmds):
    result = []
    for name, x in (("PanelSurfaceA", -1.), ("PanelSurfaceB", 1.)):
        cmds.select(clear=True)
        result.append(cmds.joint(name=name, position=(x, 0., 0.)))
    return tuple((cmds.ls(value, long=True) or [value])[0] for value in result)


def main(report: Path) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.application import EditSkinWeights
        from adv_py.core import SkinInfluenceWeight, SkinVertexWeights
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        joints = create_joints(cmds)
        source = cmds.polyPlane(name="PanelSource", width=2., height=2.,
            subdivisionsX=1, subdivisionsY=1, constructionHistory=False)[0]
        source = (cmds.ls(source, long=True) or [source])[0]
        cmds.skinCluster(*joints, source, name="PanelSourceSkin",
            maximumInfluences=2, toSelectedBones=True)
        host = MayaFaceHost()
        source_rows = []
        for index, point in enumerate(host.capture_face_mesh(source).points):
            first = (1. - point[0]) / 2.
            source_rows.append(SkinVertexWeights(index, tuple(
                SkinInfluenceWeight(joint, value) for joint, value in
                zip(joints, (first, 1. - first)) if value > 0.)))
        EditSkinWeights(host).apply("PanelSourceSkin", source, tuple(source_rows))
        controller = MayaPanelController()
        with tempfile.TemporaryDirectory(prefix="panel-surface-",
                                         dir=report.parent.resolve()) as folder:
            asset = Path(folder) / "source.json"
            exported = controller.skin_surface_source_export(":",
                "PanelSourceSkin", source, asset)
            cmds.file(new=True, force=True)
            joints = create_joints(cmds)
            target = cmds.polyPlane(name="PanelTarget", width=2., height=2.,
                subdivisionsX=2, subdivisionsY=2, constructionHistory=False)[0]
            target = (cmds.ls(target, long=True) or [target])[0]
            cmds.skinCluster(*joints, target, name="PanelTargetSkin",
                maximumInfluences=2, toSelectedBones=True)
            host = MayaFaceHost()
            before = host.capture_all_skin_weights("PanelTargetSkin", target)
            result = controller.skin_surface_transfer(":", "PanelTargetSkin",
                target, 1e-6, source_asset=asset)
            after = host.capture_all_skin_weights("PanelTargetSkin", target)
            points = host.capture_face_mesh(target).points
            center = next(i for i, point in enumerate(points)
                if abs(point[0]) < 1e-8 and abs(point[2]) < 1e-8)
            center_weights = {entry.influence_path: entry.weight
                for entry in after.vertices[center].weights}
            cmds.undo()
            undone = host.capture_all_skin_weights("PanelTargetSkin", target)
            cmds.redo()
            redone = host.capture_all_skin_weights("PanelTargetSkin", target)
            checks = {"source_asset_exported": exported == 4 and asset.is_file(),
                "cross_scene_source_absent": not cmds.objExists("PanelSource"),
                "target_complete": result.vertices == 9 and result.changed_vertices > 0,
                "center_interpolated": all(abs(center_weights.get(joint, 0.) - .5) < 1e-6
                                           for joint in joints),
                "single_undo": undone == before,
                "redo": redone == after}
        payload = {**checks, "status": "passed" if all(checks.values()) else "failed"}
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
