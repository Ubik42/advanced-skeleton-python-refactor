from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def vertices_close(left, right, tolerance=1e-6):
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if a.vertex_index != b.vertex_index or len(a.weights) != len(b.weights):
            return False
        a_weights = sorted(a.weights, key=lambda entry: entry.influence_path)
        b_weights = sorted(b.weights, key=lambda entry: entry.influence_path)
        for a_weight, b_weight in zip(a_weights, b_weights):
            if (
                a_weight.influence_path != b_weight.influence_path
                or abs(a_weight.weight - b_weight.weight) > tolerance
            ):
                return False
    return True


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BindSkin,
            EditSkinWeights,
            ExportSkinWeights,
            ImportSkinWeights,
        )
        from adv_py.core import (
            SkinInfluenceWeight,
            SkinVertexWeights,
            SkinWeightInfluenceMapping,
            SkinWeightPathMapping,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        marker = cmds.createNode(
            "transform",
            name="PortableSkinMappingSelection",
            skipSelect=True,
        )
        marker = (cmds.ls(marker, long=True) or [marker])[0]

        def joint(name, position):
            created = cmds.createNode("joint", name=name, skipSelect=True)
            cmds.xform(created, worldSpace=True, translation=position)
            return (cmds.ls(created, long=True) or [created])[0]

        source_joints = (
            joint("SourceWeightJointA", (-1.0, 0.0, 0.0)),
            joint("SourceWeightJointB", (1.0, 0.0, 0.0)),
        )
        target_joints = (
            joint("TargetWeightJointA", (-1.0, 3.0, 0.0)),
            joint("TargetWeightJointB", (1.0, 3.0, 0.0)),
        )
        source_mesh = cmds.polyPlane(
            name="SourceWeightMesh",
            width=4.0,
            height=1.0,
            subdivisionsX=3,
            subdivisionsY=1,
            constructionHistory=False,
        )[0]
        target_mesh = cmds.polyPlane(
            name="TargetWeightMesh",
            width=4.0,
            height=1.0,
            subdivisionsX=3,
            subdivisionsY=1,
            constructionHistory=False,
        )[0]
        cmds.xform(target_mesh, worldSpace=True, translation=(0.0, 3.0, 0.0))
        source_mesh = (cmds.ls(source_mesh, long=True) or [source_mesh])[0]
        target_mesh = (cmds.ls(target_mesh, long=True) or [target_mesh])[0]
        vertex_count = int(cmds.polyEvaluate(source_mesh, vertex=True))
        host = MayaBodyBuildHost()
        source_skin = "SourceWeightSkin"
        target_skin = "TargetWeightSkin"
        BindSkin(host).apply(
            source_mesh,
            source_joints,
            skin_name=source_skin,
            maximum_influences=2,
        )
        BindSkin(host).apply(
            target_mesh,
            target_joints,
            skin_name=target_skin,
            maximum_influences=2,
        )

        def weights(index, influences, first, second):
            return SkinVertexWeights(
                index,
                (
                    SkinInfluenceWeight(influences[0], first),
                    SkinInfluenceWeight(influences[1], second),
                ),
            )

        source_targets = (
            weights(0, source_joints, 0.8, 0.2),
            weights(1, source_joints, 0.5, 0.5),
            weights(2, source_joints, 0.2, 0.8),
        )
        target_before = (
            weights(0, target_joints, 0.1, 0.9),
            weights(1, target_joints, 0.9, 0.1),
            weights(2, target_joints, 0.6, 0.4),
        )
        editor = EditSkinWeights(host)
        source_edit = editor.apply(source_skin, source_mesh, source_targets)
        target_edit = editor.apply(target_skin, target_mesh, target_before)
        mapping = SkinWeightPathMapping(
            target_skin,
            target_mesh,
            tuple(
                SkinWeightInfluenceMapping(source, target)
                for source, target in zip(source_joints, target_joints)
            ),
        )
        cmds.select(marker, replace=True)
        with tempfile.TemporaryDirectory() as directory:
            weight_path = Path(directory) / "mapped_weights.json"
            ExportSkinWeights(host).apply(
                source_skin,
                source_mesh,
                weight_path,
            )
            preview = ImportSkinWeights(host).plan(
                weight_path,
                mapping=mapping,
            )
            imported = ImportSkinWeights(host).apply(
                weight_path,
                mapping=mapping,
            )
            repeated = ImportSkinWeights(host).apply(
                weight_path,
                mapping=mapping,
            )
            temporary_path = str(weight_path)

        checks = {
            "source_and_target_paths_differ": source_mesh != target_mesh
            and set(source_joints).isdisjoint(target_joints),
            "mapping_preflight_ready": preview.ready
            and len(preview.edit_plan.changes) >= 3,
            "target_document_rewritten": preview.target_document.skin_name
            == target_skin
            and preview.target_document.mesh_path == target_mesh
            and set(preview.target_document.influence_paths)
            == set(target_joints),
            "mapped_weights_imported": vertices_close(
                imported.edit_result.snapshot.vertices,
                preview.target_document.vertices,
            ),
            "repeat_import_is_noop": repeated.edit_result.changed_vertex_count
            == 0,
            "selection_preserved": (
                cmds.ls(selection=True, long=True) or []
            ) == [marker],
            "temporary_file_removed": not Path(temporary_path).exists(),
        }
        source_after = host.capture_skin_weight_input(source_edit.plan.request)
        checks["source_weights_unchanged"] = vertices_close(
            source_after.vertices,
            source_edit.snapshot.vertices,
        )
        cmds.undo()
        target_after_undo = host.capture_skin_weight_input(
            target_edit.plan.request
        )
        checks["single_undo_restored_target_weights"] = vertices_close(
            target_after_undo.vertices,
            target_edit.snapshot.vertices,
        )
        checks["both_skins_preserved_after_undo"] = cmds.objExists(
            source_skin
        ) and cmds.objExists(target_skin)
        cmds.delete(
            source_mesh,
            target_mesh,
            *source_joints,
            *target_joints,
            marker,
        )
        remaining = cmds.ls(
            "SourceWeight*",
            "TargetWeight*",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "skin_weight_explicit_mapping",
            **checks,
            "vertex_count": vertex_count,
            "mapped_influence_count": len(mapping.influences),
            "changed_vertex_count": imported.edit_result.changed_vertex_count,
            "remaining_nodes": remaining,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
