from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def _close(left, right, tolerance=1e-4):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyArmFkControls,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
            InspectBodyRebuildSafety,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="PortableArmFkSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body_before = BuildOrientedBodySkeleton(host).apply(container).snapshot
        fit_before = host.capture_fit_orientation(container)
        wrist_before = next(
            state.world_position
            for state in body_before.joints
            if state.name == "Wrist_R"
        )
        cmds.select(marker, replace=True)

        use_case = BuildBodyArmFkControls(host)
        cmds.file(modified=False)
        preview = use_case.plan(container, control_radius=2.0)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container, control_radius=2.0)
        snapshot = result.snapshot
        curves_verified = all(
            state.shape_type == "nurbsCurve" for state in snapshot.controls
        )
        zero_channels = all(
            _close(state.local_translation, (0.0, 0.0, 0.0))
            and _close(state.local_rotation, (0.0, 0.0, 0.0))
            for state in snapshot.controls
        )
        wiring_verified = all(
            state.source_control == spec.control_path
            and state.driven_joint == spec.driven_joint
            for state, spec in zip(snapshot.controls, preview.controls.controls)
        )
        body_preserved = host.capture_body_skeleton("Root_M") == body_before
        fit_preserved = host.capture_fit_orientation(container) == fit_before
        selection_preserved = (cmds.ls(selection=True) or []) == [marker]
        rebuild_blocked_by_constraints = any(
            issue.code == "external_constraint"
            for issue in InspectBodyRebuildSafety(host).execute(container).issues
        )

        shoulder_control = next(
            state.control_path
            for state in snapshot.controls
            if state.control_path.endswith("AdvPy_ShoulderFK_R")
        )
        wrist_joint = next(
            state.path for state in body_before.joints if state.name == "Wrist_R"
        )
        shoulder_joint = next(
            state.path for state in body_before.joints if state.name == "Shoulder_R"
        )
        shoulder_matrix_before = cmds.xform(
            shoulder_joint,
            query=True,
            worldSpace=True,
            matrix=True,
        )
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{shoulder_control}.rotateZ", 25.0)
        shoulder_driven = not _close(
            cmds.xform(
                shoulder_joint,
                query=True,
                worldSpace=True,
                matrix=True,
            ),
            shoulder_matrix_before,
        )
        wrist_posed = cmds.xform(
            wrist_joint,
            query=True,
            worldSpace=True,
            translation=True,
        )
        arm_pose_changed = shoulder_driven and not _close(wrist_posed, wrist_before)
        cmds.setAttr(f"{shoulder_control}.rotateZ", 0.0)
        wrist_restored = _close(
            cmds.xform(
                wrist_joint,
                query=True,
                worldSpace=True,
                translation=True,
            ),
            wrist_before,
        )
        cmds.undoInfo(stateWithoutFlush=True)

        cmds.undo()
        controls_removed = not (
            cmds.ls("AdvPy_ArmFKControls", "AdvPy_*FK*", long=True) or []
        )
        body_survived = len(host.capture_body_skeleton("Root_M").joints) == 30
        body_safe_again = InspectBodyRebuildSafety(host).execute(
            container
        ).safe_to_replace
        fit_survived_undo = host.capture_fit_orientation(container) == fit_before
        marker_survived = cmds.objExists(marker)

        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_ArmFKControls",
            "AdvPy_*FK*",
            marker,
            long=True,
        ) or []
        passed = all(
            (
                preview.ready,
                preview_clean,
                len(preview.controls.controls) == 6,
                len(snapshot.controls) == 6,
                curves_verified,
                zero_channels,
                wiring_verified,
                body_preserved,
                fit_preserved,
                selection_preserved,
                rebuild_blocked_by_constraints,
                arm_pose_changed,
                wrist_restored,
                controls_removed,
                body_survived,
                body_safe_again,
                fit_survived_undo,
                marker_survived,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_bilateral_arm_fk_controls",
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "planned_control_count": len(preview.controls.controls),
            "created_control_count": len(snapshot.controls),
            "nurbs_curves_verified": curves_verified,
            "control_channels_zero": zero_channels,
            "constraint_wiring_verified": wiring_verified,
            "body_bind_pose_preserved": body_preserved,
            "fit_source_preserved": fit_preserved,
            "selection_preserved": selection_preserved,
            "rebuild_blocked_while_constraints_exist": rebuild_blocked_by_constraints,
            "fk_pose_changed_body_arm": arm_pose_changed,
            "zero_pose_restored_wrist": wrist_restored,
            "single_undo_removed_controls": controls_removed,
            "body_survived_undo": body_survived,
            "body_rebuild_safe_after_undo": body_safe_again,
            "fit_source_survived_undo": fit_survived_undo,
            "unrelated_node_survived": marker_survived,
            "cleanup": not remaining,
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
