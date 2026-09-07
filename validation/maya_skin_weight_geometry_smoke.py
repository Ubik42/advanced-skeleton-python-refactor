from __future__ import annotations

import json
import os
import sys
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
        for a_weight, b_weight in zip(
            sorted(a.weights, key=lambda entry: entry.influence_path),
            sorted(b.weights, key=lambda entry: entry.influence_path),
        ):
            if (
                a_weight.influence_path != b_weight.influence_path
                or abs(a_weight.weight - b_weight.weight) > tolerance
            ):
                return False
    return True


def points(cmds, mesh, indices):
    values = []
    for index in indices:
        values.extend(
            cmds.xform(
                f"{mesh}.vtx[{index}]",
                query=True,
                worldSpace=True,
                translation=True,
            ) or []
        )
    return tuple(float(value) for value in values)


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BindSkin,
            EditSkinWeights,
            MirrorSkinWeightsByGeometry,
        )
        from adv_py.core import (
            SkinInfluenceWeight,
            SkinVertexWeights,
            SkinWeightInfluenceMapping,
            SkinWeightMirrorDirection,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        marker = cmds.createNode(
            "transform",
            name="GeometryMirrorSelection",
            skipSelect=True,
        )
        marker = (cmds.ls(marker, long=True) or [marker])[0]

        def joint(name, x):
            created = cmds.createNode("joint", name=name, skipSelect=True)
            cmds.xform(created, worldSpace=True, translation=(x, 0.0, 0.0))
            return (cmds.ls(created, long=True) or [created])[0]

        right_a = joint("GeometryInfluenceA_R", -2.0)
        right_b = joint("GeometryInfluenceB_R", -1.0)
        center = joint("GeometryInfluence_M", 0.0)
        left_b = joint("GeometryInfluenceB_L", 1.0)
        left_a = joint("GeometryInfluenceA_L", 2.0)
        influences = (right_a, right_b, center, left_b, left_a)
        mesh = cmds.polyPlane(
            name="GeometryMirrorMesh",
            width=4.0,
            height=1.0,
            subdivisionsX=3,
            subdivisionsY=1,
            constructionHistory=False,
        )[0]
        mesh = (cmds.ls(mesh, long=True) or [mesh])[0]
        vertex_count = int(cmds.polyEvaluate(mesh, vertex=True))
        host = MayaBodyBuildHost()
        skin_name = "AdvPy_GeometryMirrorSkin"
        BindSkin(host).apply(
            mesh,
            influences,
            skin_name=skin_name,
            maximum_influences=3,
        )

        geometry = host.capture_mesh_vertex_positions(mesh)
        source_indices = tuple(
            vertex.vertex_index
            for vertex in geometry.vertices
            if vertex.position[0] < -1e-5
        )
        target_indices = tuple(
            vertex.vertex_index
            for vertex in geometry.vertices
            if vertex.position[0] > 1e-5
        )

        def weights(index, *values):
            return SkinVertexWeights(
                index,
                tuple(
                    SkinInfluenceWeight(path, weight)
                    for path, weight in values
                ),
            )

        source_weights = tuple(
            weights(
                index,
                (right_a if order % 2 == 0 else right_b, 0.7),
                (center, 0.3),
            )
            for order, index in enumerate(source_indices)
        )
        target_before = tuple(
            weights(index, (left_a, 0.2), (left_b, 0.8))
            for index in target_indices
        )
        EditSkinWeights(host).apply(
            skin_name,
            mesh,
            source_weights + target_before,
        )
        mapping = (
            SkinWeightInfluenceMapping(right_a, left_a),
            SkinWeightInfluenceMapping(right_b, left_b),
            SkinWeightInfluenceMapping(center, center),
        )
        cmds.select(marker, replace=True)
        operation = MirrorSkinWeightsByGeometry(host)
        preview = operation.plan(
            skin_name,
            mesh,
            SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE,
            mapping,
        )
        if not preview.ready or preview.mirror_plan is None:
            raise RuntimeError("几何权重镜像预检未通过")
        mirrored = operation.apply(
            skin_name,
            mesh,
            SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE,
            mapping,
        )
        repeated = operation.apply(
            skin_name,
            mesh,
            SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE,
            mapping,
        )

        pairs = preview.vertex_pairs
        expected_targets = preview.mirror_plan.edit_plan.request.vertices
        source_after = host.capture_skin_vertices(
            skin_name,
            mesh,
            source_indices,
        )
        target_rest_points = points(cmds, mesh, target_indices)
        source_rest_points = points(cmds, mesh, source_indices)
        left_a_position = cmds.xform(
            left_a,
            query=True,
            worldSpace=True,
            translation=True,
        )
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.xform(
            left_a,
            worldSpace=True,
            translation=(left_a_position[0], 1.0, left_a_position[2]),
        )
        target_posed_points = points(cmds, mesh, target_indices)
        source_posed_points = points(cmds, mesh, source_indices)
        cmds.xform(left_a, worldSpace=True, translation=left_a_position)
        cmds.undoInfo(stateWithoutFlush=True)
        target_displacement = max(
            abs(a - b) for a, b in zip(target_rest_points, target_posed_points)
        )
        source_displacement = max(
            abs(a - b) for a, b in zip(source_rest_points, source_posed_points)
        )

        checks = {
            "geometry_snapshot_complete": geometry.vertex_count == vertex_count
            and len(geometry.vertices) == vertex_count,
            "preflight_ready": preview.ready
            and len(pairs) == len(source_indices) == len(target_indices),
            "all_pairs_reflect_across_x": all(
                abs(
                    geometry.vertices[pair.source_index].position[0]
                    + geometry.vertices[pair.target_index].position[0]
                ) < 1e-5
                and all(
                    abs(
                        geometry.vertices[pair.source_index].position[axis]
                        - geometry.vertices[pair.target_index].position[axis]
                    ) < 1e-5
                    for axis in (1, 2)
                )
                for pair in pairs
            ),
            "target_weights_mirrored": vertices_close(
                mirrored.mirror_result.edit_result.snapshot.vertices,
                expected_targets,
            ),
            "source_weights_unchanged": vertices_close(
                source_after.vertices,
                source_weights,
            ),
            "repeat_is_noop": repeated.mirror_result.edit_result.changed_vertex_count == 0,
            "mapped_target_deforms": target_displacement > 0.05,
            "source_isolated_from_target_influence": source_displacement < 1e-5,
            "selection_preserved": (
                cmds.ls(selection=True, long=True) or []
            ) == [marker],
        }
        cmds.undo()
        target_after_undo = host.capture_skin_vertices(
            skin_name,
            mesh,
            target_indices,
        )
        checks["single_undo_restored_target"] = vertices_close(
            target_after_undo.vertices,
            target_before,
        )
        checks["source_preserved_after_undo"] = vertices_close(
            host.capture_skin_vertices(
                skin_name,
                mesh,
                source_indices,
            ).vertices,
            source_weights,
        )
        checks["skin_preserved_after_undo"] = cmds.objExists(skin_name)
        cmds.delete(mesh, *influences, marker)
        remaining = cmds.ls(
            "GeometryMirrorMesh",
            "GeometryInfluence*",
            skin_name,
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "geometry_paired_skin_weight_mirror",
            **checks,
            "vertex_count": vertex_count,
            "source_vertex_count": len(source_indices),
            "target_vertex_count": len(target_indices),
            "generated_pair_count": len(pairs),
            "influence_mapping_count": len(mapping),
            "target_displacement": round(target_displacement, 6),
            "source_displacement": round(source_displacement, 6),
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
