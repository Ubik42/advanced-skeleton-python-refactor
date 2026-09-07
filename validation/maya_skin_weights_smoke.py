from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def vertex_points(cmds, mesh, indices):
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


def vertices_close(left, right, tolerance=1e-6):
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if a.vertex_index != b.vertex_index or len(a.weights) != len(b.weights):
            return False
        for a_weight, b_weight in zip(a.weights, b.weights):
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
        )
        from adv_py.core import (
            BodyArmTwistSegment,
            FitBuildSide,
            SkinInfluenceWeight,
            SkinVertexWeights,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableSkinWeightSelection",
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
            name="PortableArmWeightMesh",
            radius=0.45,
            height=length,
            axis=axis,
            subdivisionsX=12,
            subdivisionsY=5,
            constructionHistory=False,
        )[0]
        cmds.xform(mesh, worldSpace=True, translation=midpoint)
        mesh = (cmds.ls(mesh, long=True) or [mesh])[0]
        mesh_vertex_count = int(cmds.polyEvaluate(mesh, vertex=True))

        rig = BuildBodyArmRig(host).apply(container, twist_joints_per_segment=2)
        influences = tuple(
            spec.path
            for spec in rig.plan.twist.joints
            if spec.side is FitBuildSide.RIGHT
            and spec.segment is BodyArmTwistSegment.LOWER
        )
        skin_name = "AdvPy_ArmWeightSkin"
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

        targets = (
            weights(0, 0.8, 0.2),
            weights(1, 0.5, 0.5),
            weights(2, 0.2, 0.8),
        )
        cmds.select(marker, replace=True)
        editor = EditSkinWeights(host)
        preview = editor.plan(skin_name, mesh, targets)
        result = editor.apply(skin_name, mesh, targets)
        repeated = editor.apply(skin_name, mesh, targets)
        rest_points = vertex_points(cmds, mesh, (0, 1, 2))

        cmds.undoInfo(stateWithoutFlush=False)
        wrist_control = next(
            limb.wrist_control_path
            for limb in rig.ik.limbs
            if limb.side is FitBuildSide.RIGHT
        )
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 1.0)
        cmds.setAttr(f"{wrist_control}.rotateX", 60.0)
        posed_points = vertex_points(cmds, mesh, (0, 1, 2))
        maximum_displacement = max(
            abs(a - b) for a, b in zip(rest_points, posed_points)
        )
        cmds.setAttr(f"{wrist_control}.rotateX", 0.0)
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "preflight_ready": preview.ready and bool(preview.changes),
            "exact_weights_written": not result.plan.input_issues
            and vertices_close(result.snapshot.vertices, result.plan.request.vertices),
            "repeat_is_noop": repeated.changed_vertex_count == 0,
            "weighted_vertices_deform": maximum_displacement > 0.05,
            "selection_preserved": (
                cmds.ls(selection=True, long=True) or []
            ) == [marker],
        }
        cmds.undo()
        restored = host.capture_skin_weight_input(preview.request)
        checks["single_undo_restored_weights"] = vertices_close(
            restored.vertices,
            preview.input_state.vertices,
        )
        checks["skin_preserved_after_weight_undo"] = cmds.objExists(skin_name)
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
            "PortableArmWeightMesh",
            "AdvPy_ArmWeightSkin",
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
            "slice": "explicit_skin_weights",
            **checks,
            "vertex_count": mesh_vertex_count,
            "edited_vertex_count": result.changed_vertex_count,
            "influence_count": len(influences),
            "maximum_displacement": round(maximum_displacement, 6),
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
