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
            BuildBodyArmRig,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            EditSkinWeights,
            ExportSkinWeights,
            ImportSkinWeights,
        )
        from adv_py.core import (
            BodyArmTwistSegment,
            FitBuildSide,
            FitSkeletonValidationError,
            SkinInfluenceWeight,
            SkinVertexWeights,
            skin_weight_document_from_json,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableSkinWeightIoSelection",
            skipSelect=True,
        )
        marker = (cmds.ls(marker, long=True) or [marker])[0]
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot

        elbow = next(joint for joint in body.joints if joint.name == "Elbow_R")
        wrist = next(joint for joint in body.joints if joint.name == "Wrist_R")
        direction = tuple(
            b - a for a, b in zip(elbow.world_position, wrist.world_position)
        )
        length = sum(value * value for value in direction) ** 0.5
        axis = tuple(value / length for value in direction)
        midpoint = tuple(
            (a + b) * 0.5
            for a, b in zip(elbow.world_position, wrist.world_position)
        )
        mesh = cmds.polyCylinder(
            name="PortableArmWeightIoMesh",
            radius=0.45,
            height=length,
            axis=axis,
            subdivisionsX=12,
            subdivisionsY=5,
            constructionHistory=False,
        )[0]
        cmds.xform(mesh, worldSpace=True, translation=midpoint)
        mesh = (cmds.ls(mesh, long=True) or [mesh])[0]
        vertex_count = int(cmds.polyEvaluate(mesh, vertex=True))

        rig = BuildBodyArmRig(host).apply(container, twist_joints_per_segment=2)
        influences = tuple(
            spec.path
            for spec in rig.plan.twist.joints
            if spec.side is FitBuildSide.RIGHT
            and spec.segment is BodyArmTwistSegment.LOWER
        )
        skin_name = "AdvPy_ArmWeightIoSkin"
        BindSkin(host).apply(
            mesh,
            influences,
            skin_name=skin_name,
            maximum_influences=2,
        )

        def weights(index, first, second):
            return SkinVertexWeights(
                index,
                (
                    SkinInfluenceWeight(influences[0], first),
                    SkinInfluenceWeight(influences[1], second),
                ),
            )

        saved_targets = (
            weights(0, 0.8, 0.2),
            weights(1, 0.5, 0.5),
            weights(2, 0.2, 0.8),
        )
        altered_targets = (
            weights(0, 0.1, 0.9),
            weights(1, 0.9, 0.1),
            weights(2, 0.6, 0.4),
        )
        editor = EditSkinWeights(host)
        editor.apply(skin_name, mesh, saved_targets)
        cmds.select(marker, replace=True)

        export_blocked = False
        with tempfile.TemporaryDirectory() as directory:
            weight_path = Path(directory) / "arm_weights.json"
            export_result = ExportSkinWeights(host).apply(
                skin_name,
                mesh,
                weight_path,
            )
            document = skin_weight_document_from_json(
                weight_path.read_text(encoding="utf-8")
            )
            try:
                ExportSkinWeights(host).apply(skin_name, mesh, weight_path)
            except FitSkeletonValidationError:
                export_blocked = True

            altered = editor.apply(skin_name, mesh, altered_targets)
            import_preview = ImportSkinWeights(host).plan(weight_path)
            imported = ImportSkinWeights(host).apply(weight_path)
            repeated = ImportSkinWeights(host).apply(weight_path)
            temporary_path = str(weight_path)

        imported_first_three = imported.edit_result.snapshot.vertices[:3]
        checks = {
            "document_schema_valid": document.schema_version == 1
            and len(document.content_sha256) == 64,
            "all_vertices_exported": len(document.vertices) == vertex_count,
            "existing_file_not_overwritten": export_blocked,
            "import_preflight_ready": import_preview.ready
            and len(import_preview.edit_plan.changes) == 3,
            "import_restored_saved_weights": vertices_close(
                imported_first_three,
                saved_targets,
            ),
            "repeat_import_is_noop": repeated.edit_result.changed_vertex_count == 0,
            "selection_preserved": (
                cmds.ls(selection=True, long=True) or []
            ) == [marker],
            "temporary_file_removed": not Path(temporary_path).exists(),
            "nonempty_export": export_result.bytes_written > 0,
        }
        cmds.undo()
        restored_after_undo = host.capture_skin_weight_input(altered.plan.request)
        checks["single_undo_restored_preimport_weights"] = vertices_close(
            restored_after_undo.vertices,
            altered.snapshot.vertices,
        )
        checks["skin_preserved_after_import_undo"] = cmds.objExists(skin_name)
        cmds.delete(
            mesh,
            "|AdvPy_ArmMechanisms",
            "|AdvPy_ArmFKControls",
            "|AdvPy_ArmIKControls",
            "|AdvPy_ArmSettings",
            "|AdvPy_ArmTwistJoints",
            "|Root_M",
            container,
            marker,
        )
        remaining = cmds.ls(
            "PortableArmWeightIoMesh",
            skin_name,
            "AdvPy_Arm*",
            "Root_M",
            "FitSkeleton",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "skin_weight_json_round_trip",
            **checks,
            "vertex_count": vertex_count,
            "exported_vertex_count": len(document.vertices),
            "imported_vertex_count": imported.edit_result.changed_vertex_count,
            "exported_bytes": export_result.bytes_written,
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
