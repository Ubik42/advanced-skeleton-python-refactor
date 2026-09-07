from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def points(cmds, mesh):
    values = cmds.xform(f"{mesh}.vtx[*]", query=True, worldSpace=True, translation=True) or []
    return tuple(float(value) for value in values)


def close(left, right, tolerance=1e-4):
    return len(left) == len(right) and all(abs(a - b) <= tolerance for a, b in zip(left, right))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BindSkin, BuildBodyArmRig, BuildOrientedBodySkeleton, BuildSyntheticBodySourceFit, CreateFitSkeleton
        from adv_py.core import BodyArmTwistSegment, FitBuildSide

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="PortableSkinBindSelection", skipSelect=True)
        marker = (cmds.ls(marker, long=True) or [marker])[0]
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot

        elbow = next(joint for joint in body.joints if joint.name == "Elbow_R")
        wrist = next(joint for joint in body.joints if joint.name == "Wrist_R")
        direction = tuple(b - a for a, b in zip(elbow.world_position, wrist.world_position))
        length = sum(value * value for value in direction) ** 0.5
        axis = tuple(value / length for value in direction)
        midpoint = tuple((a + b) * 0.5 for a, b in zip(elbow.world_position, wrist.world_position))
        mesh = cmds.polyCylinder(
            name="PortableArmSkinMesh",
            radius=0.45,
            height=length,
            axis=axis,
            subdivisionsX=12,
            subdivisionsY=5,
            constructionHistory=False,
        )[0]
        cmds.xform(mesh, worldSpace=True, translation=midpoint)
        mesh = (cmds.ls(mesh, long=True) or [mesh])[0]

        rig = BuildBodyArmRig(host).apply(container, twist_joints_per_segment=2)
        influences = tuple(
            spec.path
            for spec in rig.plan.twist.joints
            if spec.side is FitBuildSide.RIGHT and spec.segment is BodyArmTwistSegment.LOWER
        )
        cmds.select(marker, replace=True)
        binder = BindSkin(host)
        preview = binder.plan(mesh, influences, skin_name="AdvPy_ArmDemoSkin", maximum_influences=2)
        before = points(cmds, mesh)
        result = binder.apply(mesh, influences, skin_name="AdvPy_ArmDemoSkin", maximum_influences=2)
        repeated = binder.plan(mesh, influences, skin_name="AdvPy_ArmDemoSkin2", maximum_influences=2)

        cmds.undoInfo(stateWithoutFlush=False)
        wrist_control = next(limb.wrist_control_path for limb in rig.ik.limbs if limb.side is FitBuildSide.RIGHT)
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 1.0)
        cmds.setAttr(f"{wrist_control}.rotateX", 60.0)
        posed = points(cmds, mesh)
        maximum_displacement = max(abs(a - b) for a, b in zip(before, posed))
        cmds.setAttr(f"{wrist_control}.rotateX", 0.0)
        cmds.setAttr("|AdvPy_ArmSettings.armIkFk_R", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "preflight_ready": preview.ready,
            "explicit_geometry": result.snapshot.geometry_paths == (mesh,),
            "explicit_influences": set(result.snapshot.influence_paths) == set(influences),
            "maximum_two_influences": result.snapshot.maximum_influences == 2 and result.snapshot.maintain_maximum_influences,
            "repeat_bind_blocked": not repeated.ready and any(issue.code == "already_skinned" for issue in repeated.input_issues),
            "twist_pose_deforms_mesh": maximum_displacement > 0.05,
            "selection_preserved": (cmds.ls(selection=True, long=True) or []) == [marker],
        }
        cmds.undo()
        checks["single_undo_removed_skin"] = not cmds.objExists("AdvPy_ArmDemoSkin") and cmds.objExists(mesh)
        checks["undo_restored_mesh"] = close(before, points(cmds, mesh))
        checks["rig_preserved_after_skin_undo"] = cmds.objExists("|AdvPy_ArmTwistJoints")
        cmds.delete(mesh, "|AdvPy_ArmMechanisms", "|AdvPy_ArmFKControls", "|AdvPy_ArmIKControls", "|AdvPy_ArmSettings", "|AdvPy_ArmTwistJoints", "|Root_M", container, marker)
        remaining = cmds.ls("PortableArmSkinMesh", "AdvPy_ArmDemoSkin*", "AdvPy_Arm*", "Root_M", "FitSkeleton", marker, long=True) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "explicit_skin_bind",
            **checks,
            "vertex_count": len(before) // 3,
            "influence_count": len(influences),
            "maximum_displacement": round(maximum_displacement, 6),
            "remaining_nodes": remaining,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
