"""Check chunked API skin snapshots against Maya commands beyond 4096 vertices."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import EditSkinWeights
        from adv_py.core import (SkinInfluenceWeight, SkinVertexWeights,
            skin_weight_document_from_state)

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        joints = []
        for index, position in enumerate(((-1., -1.), (1., -1.), (-1., 1.), (1., 1.))):
            cmds.select(clear=True)
            joint = cmds.joint(name=f"BulkJoint{index}",
                               position=(position[0], 0., position[1]))
            joints.append((cmds.ls(joint, long=True) or [joint])[0])
        mesh = cmds.polyPlane(name="BulkMesh", width=2., height=2.,
            subdivisionsX=70, subdivisionsY=70, constructionHistory=False)[0]
        mesh = (cmds.ls(mesh, long=True) or [mesh])[0]
        skin = cmds.skinCluster(*joints, mesh, name="BulkSkin",
            maximumInfluences=4, toSelectedBones=True)[0]
        marker = cmds.createNode("transform", name="BulkSelectionMarker")
        marker = (cmds.ls(marker, long=True) or [marker])[0]
        cmds.select(marker, replace=True)
        host = MayaBodyBuildHost()
        captured_at = time.perf_counter()
        state = host.capture_all_skin_weights(skin, mesh)
        capture_seconds = time.perf_counter() - captured_at
        document = skin_weight_document_from_state(state)
        samples = (0, 1, 4095, 4096, 5040)
        sparse_indices = tuple(reversed(samples))
        sparse_at = time.perf_counter()
        sparse = host.capture_skin_vertices(skin, mesh, sparse_indices)
        sparse_seconds = time.perf_counter() - sparse_at
        comparisons = []
        for index in samples:
            actual = {entry.influence_path: entry.weight
                      for entry in state.vertices[index].weights}
            for joint in joints:
                expected = float(cmds.skinPercent(skin, f"{mesh}.vtx[{index}]",
                                                  query=True, transform=joint))
                comparisons.append(abs(actual.get(joint, 0.) - expected) < 1e-7)
        checks = {"all_vertices_captured": state.vertex_count == 5041
                  and len(state.vertices) == 5041,
                  "chunk_boundary_matches_commands": all(comparisons),
                  "sparse_order_and_values_match": tuple(row.vertex_index for row in sparse.vertices)
                  == sparse_indices and all(row == state.vertices[row.vertex_index]
                                            for row in sparse.vertices),
                  "document_complete": len(document.vertices) == 5041,
                  "selection_preserved": (cmds.ls(selection=True, long=True) or []) == [marker]}
        edited = list(state.vertices)
        for index in (4095, 4096):
            edited[index] = SkinVertexWeights(index, (
                SkinInfluenceWeight(joints[0], .6),
                SkinInfluenceWeight(joints[1], .4)))
        applied = EditSkinWeights(host).apply(skin, mesh, tuple(edited))
        after = host.capture_all_skin_weights(skin, mesh)
        cmds.undo()
        undone = host.capture_all_skin_weights(skin, mesh)
        cmds.redo()
        redone = host.capture_all_skin_weights(skin, mesh)
        checks["full_request_changes_only_boundary"] = applied.changed_vertex_count == 2
        checks["single_undo_restores_full_snapshot"] = undone == state
        checks["redo_restores_full_snapshot"] = redone == after
        payload = {"host": "maya", "version": str(cmds.about(version=True)),
            "pid": os.getpid(), "slice": "skin_bulk_api_capture",
            **checks, "capture_seconds": round(capture_seconds, 3),
            "sparse_capture_seconds": round(sparse_seconds, 3),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if all(checks.values()) else "failed"}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
