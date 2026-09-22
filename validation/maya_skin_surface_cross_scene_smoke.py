"""Run source export, target transfer and saved-scene readback in separate Maya processes."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def joints(cmds):
    result = []
    for name, x in (("SurfaceJointA", -1.), ("SurfaceJointB", 1.)):
        cmds.select(clear=True)
        result.append(cmds.joint(name=name, position=(x, 0., 0.)))
    return tuple((cmds.ls(joint, long=True) or [joint])[0] for joint in result)


def run(mode: str, directory: Path) -> int:
    directory = directory.resolve()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.application import (CaptureSkinWeightSurfaceSource,
            EditSkinWeights, TransferSkinWeightsBySurface,
            load_skin_weight_surface_source, save_skin_weight_surface_source)
        from adv_py.core import SkinInfluenceWeight, SkinVertexWeights

        directory.mkdir(parents=True, exist_ok=True)
        asset_path = directory / "source_asset.json"
        target_scene = directory / "transferred.ma"
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        influences = joints(cmds)
        host = MayaFaceHost()
        if mode == "source":
            mesh = cmds.polyPlane(name="SourceMesh", width=2., height=2.,
                subdivisionsX=1, subdivisionsY=1, constructionHistory=False)[0]
            mesh = (cmds.ls(mesh, long=True) or [mesh])[0]
            cmds.skinCluster(*influences, mesh, name="SourceSkin",
                maximumInfluences=2, toSelectedBones=True)
            rows = []
            for index, point in enumerate(host.capture_face_mesh(mesh).points):
                first = (1. - point[0]) / 2.
                rows.append(SkinVertexWeights(index, tuple(
                    SkinInfluenceWeight(joint, value)
                    for joint, value in zip(influences, (first, 1. - first))
                    if value > 0.)))
            EditSkinWeights(host).apply("SourceSkin", mesh, tuple(rows))
            source = CaptureSkinWeightSurfaceSource(host).execute("SourceSkin", mesh)
            save_skin_weight_surface_source(source, asset_path)
            cmds.file(rename=str(directory / "source_scene.ma"))
            cmds.file(save=True, type="mayaAscii", force=True)
            payload = {"source_vertices": source.weights.vertex_count,
                       "source_triangles": len(source.geometry.triangles)}
        elif mode == "target":
            source = load_skin_weight_surface_source(asset_path)
            mesh = cmds.polyPlane(name="TargetMesh", width=2., height=2.,
                subdivisionsX=2, subdivisionsY=2, constructionHistory=False)[0]
            mesh = (cmds.ls(mesh, long=True) or [mesh])[0]
            cmds.skinCluster(*influences, mesh, name="TargetSkin",
                maximumInfluences=2, toSelectedBones=True)
            cmds.file(rename=str(directory / "target_before.ma"))
            cmds.file(save=True, type="mayaAscii", force=True)
            operation = TransferSkinWeightsBySurface(host)
            before = host.capture_all_skin_weights("TargetSkin", mesh)
            plan, result = operation.apply_from_documents(source.weights,
                source.geometry, "TargetSkin", mesh, max_distance=1e-6)
            after = host.capture_all_skin_weights("TargetSkin", mesh)
            cmds.undo()
            undone = host.capture_all_skin_weights("TargetSkin", mesh)
            cmds.redo()
            redone = host.capture_all_skin_weights("TargetSkin", mesh)
            cmds.file(rename=str(target_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            payload = {"target_vertices": plan.transfer.document.vertex_count,
                       "source_mesh_absent": not cmds.objExists("SourceMesh"),
                       "changed": result.changed_vertex_count,
                       "undo_restored": undone == before,
                       "redo_restored": redone == after}
        elif mode == "target_aligned":
            source = load_skin_weight_surface_source(asset_path)
            mesh = cmds.polyPlane(name="TargetMesh", width=2., height=2.,
                subdivisionsX=2, subdivisionsY=2, constructionHistory=False)[0]
            mesh = (cmds.ls(mesh, long=True) or [mesh])[0]
            original = host.capture_face_mesh(mesh)
            pairs = []
            for source_index in (0, 1, 2):
                source_point = source.geometry.mesh.points[source_index]
                target_index = next(index for index, point in enumerate(original.points)
                    if all(abs(a - b) < 1e-8 for a, b in zip(point, source_point)))
                pairs.append((source_index, target_index))
            for index, point in enumerate(original.points):
                cmds.xform(f"{mesh}.vtx[{index}]", objectSpace=True,
                    translation=(5. + point[2], point[1], 2. - point[0]))
            cmds.skinCluster(*influences, mesh, name="TargetSkin",
                maximumInfluences=2, toSelectedBones=True)
            alignment = {"pairs": pairs, "max_residual": 1e-6}
            (directory / "alignment.json").write_text(
                json.dumps(alignment, indent=2) + "\n", encoding="utf-8")
            cmds.file(rename=str(directory / "target_before_aligned.ma"))
            cmds.file(save=True, type="mayaAscii", force=True)
            payload = {"source_mesh_absent": not cmds.objExists("SourceMesh"),
                       "target_vertices": len(host.capture_face_mesh(mesh).points),
                       "alignment_pairs": pairs}
        elif mode == "inspect":
            scene_name = sys.argv[3] if len(sys.argv) > 3 else "transferred.ma"
            cmds.file(directory / scene_name,
                      open=True, force=True)
            mesh = "|TargetMesh"
            state = host.capture_all_skin_weights("TargetSkin", mesh)
            points = host.capture_face_mesh(mesh).points
            center_position = (5., 2.) if "aligned" in scene_name else (0., 0.)
            center = next(i for i, point in enumerate(points)
                          if abs(point[0] - center_position[0]) < 1e-8
                          and abs(point[2] - center_position[1]) < 1e-8)
            center_weights = {entry.influence_path: entry.weight
                              for entry in state.vertices[center].weights}
            payload = {"reopened_vertices": state.vertex_count,
                "center_interpolated": all(abs(center_weights.get(joint, 0.) - .5) < 1e-6
                                           for joint in influences),
                "source_mesh_absent": not cmds.objExists("SourceMesh")}
        else:
            raise ValueError(mode)
        (directory / (mode + ".json")).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if mode == "source":
            return 0 if payload["source_vertices"] == 4 else 1
        if mode == "target":
            return 0 if all((payload["target_vertices"] == 9,
                payload["source_mesh_absent"], payload["changed"] > 0,
                payload["undo_restored"], payload["redo_restored"])) else 1
        if mode == "target_aligned":
            return 0 if payload["source_mesh_absent"] and payload["target_vertices"] == 9 else 1
        return 0 if all((payload["reopened_vertices"] == 9,
            payload["center_interpolated"], payload["source_mesh_absent"])) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1], Path(sys.argv[2])))
