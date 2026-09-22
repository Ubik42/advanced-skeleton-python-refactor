"""Standalone Maya acceptance with self-generated meshes of different topology."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(output: Path, subdivisions: int = 2) -> int:
    start = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.application import EditSkinWeights, TransferSkinWeightsBySurface
        from adv_py.core import SkinInfluenceWeight, SkinVertexWeights

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        joints = []
        for name, x in (("SurfaceJointA", -1.), ("SurfaceJointB", 1.)):
            cmds.select(clear=True)
            joints.append(cmds.joint(name=name, position=(x, 0., 0.)))
        joints = tuple((cmds.ls(joint, long=True) or [joint])[0] for joint in joints)
        source = cmds.polyPlane(name="SurfaceSource", width=2., height=2.,
                                subdivisionsX=1, subdivisionsY=1,
                                constructionHistory=False)[0]
        target = cmds.polyPlane(name="SurfaceTarget", width=2., height=2.,
                                subdivisionsX=subdivisions, subdivisionsY=subdivisions,
                                constructionHistory=False)[0]
        source = (cmds.ls(source, long=True) or [source])[0]
        target = (cmds.ls(target, long=True) or [target])[0]
        cmds.skinCluster(*joints, source, name="SurfaceSourceSkin",
                         maximumInfluences=2, toSelectedBones=True)
        cmds.skinCluster(*joints, target, name="SurfaceTargetSkin",
                         maximumInfluences=2, toSelectedBones=True)
        host = MayaFaceHost()
        source_geometry = host.capture_face_mesh(source)
        rows = []
        for index, point in enumerate(source_geometry.points):
            first = (1. - point[0]) / 2.
            weights = tuple(SkinInfluenceWeight(joint, value)
                for joint, value in zip(joints, (first, 1. - first)) if value > 0.)
            rows.append(SkinVertexWeights(index, weights))
        EditSkinWeights(host).apply("SurfaceSourceSkin", source, tuple(rows))
        before_source = host.capture_all_skin_weights("SurfaceSourceSkin", source)
        before_target = host.capture_all_skin_weights("SurfaceTargetSkin", target)
        operation = TransferSkinWeightsBySurface(host)
        transfer_started = time.perf_counter()
        preview = operation.plan("SurfaceSourceSkin", source,
            "SurfaceTargetSkin", target, max_distance=1e-6)
        result = operation.apply("SurfaceSourceSkin", source,
            "SurfaceTargetSkin", target, max_distance=1e-6)
        transfer_seconds = time.perf_counter() - transfer_started
        after_target = host.capture_all_skin_weights("SurfaceTargetSkin", target)
        expected = {row.vertex_index: row.weights for row in result.plan.transfer.document.vertices}
        actual = {row.vertex_index: row.weights for row in after_target.vertices}
        matches = all(len(expected[i]) == len(actual[i]) and all(
            a.influence_path == b.influence_path and abs(a.weight - b.weight) < 1e-6
            for a, b in zip(expected[i], actual[i])) for i in expected)
        mismatches = [(i, [(w.influence_path, w.weight) for w in expected[i]],
                       [(w.influence_path, w.weight) for w in actual[i]])
                      for i in expected if len(expected[i]) != len(actual[i]) or any(
                          a.influence_path != b.influence_path or abs(a.weight - b.weight) >= 1e-6
                          for a, b in zip(expected[i], actual[i]))]
        neutral = host.capture_face_mesh(target)
        center = next(i for i, point in enumerate(neutral.points)
                      if abs(point[0]) < 1e-8 and abs(point[2]) < 1e-8)
        center_weights = {row.influence_path: row.weight for row in actual[center]}
        cmds.undo()
        undone = host.capture_all_skin_weights("SurfaceTargetSkin", target)
        cmds.redo()
        redone = host.capture_all_skin_weights("SurfaceTargetSkin", target)
        checks = {
            "different_topology": len(before_source.vertices) == 4
                and len(before_target.vertices) == (subdivisions + 1) ** 2,
            "complete_target_document": len(preview.transfer.document.vertices)
                == (subdivisions + 1) ** 2,
            "all_weights_match": matches,
            "center_interpolated": all(abs(center_weights.get(joint, 0.) - .5) < 1e-6
                                       for joint in joints),
            "source_unchanged": host.capture_all_skin_weights("SurfaceSourceSkin", source) == before_source,
            "single_undo_restores_target": undone == before_target,
            "redo_restores_transfer": redone == after_target,
            "vertices_changed": result.edit_result.changed_vertex_count > 0,
        }
        payload = {"host": "maya", "version": str(cmds.about(version=True)),
            "pid": os.getpid(), "slice": "skin_weight_surface_transfer",
            "target_vertices": (subdivisions + 1) ** 2,
            "changed_vertices": result.edit_result.changed_vertex_count,
            "mismatch_count": len(mismatches),
            "mismatch_examples": mismatches[:3],
            "transfer_seconds": round(transfer_seconds, 3),
            **checks, "duration_seconds": round(time.perf_counter() - start, 3),
            "status": "passed" if all(checks.values()) else "failed"}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 2))
