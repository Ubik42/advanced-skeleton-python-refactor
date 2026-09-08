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

        from adv_py.adapters import MayaBodyBuildHost, MayaMocapConnectionHost
        from adv_py.application import (
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            ConnectMocapBody,
            CreateFitSkeleton,
            DisconnectMocapBody,
        )
        from adv_py.core import MocapJointMapping

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        body_host = MayaBodyBuildHost()
        container = CreateFitSkeleton(body_host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(body_host).apply(container)
        body = BuildOrientedBodySkeleton(body_host).apply(container).snapshot

        cmds.namespace(add="TakeA")
        hips = cmds.createNode("joint", name="TakeA:Hips", skipSelect=True)
        spine = cmds.createNode("joint", name="TakeA:Spine", parent=hips, skipSelect=True)
        chest = cmds.createNode("joint", name="TakeA:Chest", parent=spine, skipSelect=True)
        neck = cmds.createNode("joint", name="TakeA:Neck", parent=chest, skipSelect=True)
        cmds.createNode("joint", name="TakeA:Head", parent=neck, skipSelect=True)
        marker = cmds.createNode("transform", name="MocapConnectionSelection", skipSelect=True)
        for frame, hips_x, hips_yaw, spine_pitch in (
            (1, 0.0, 0.0, 0.0),
            (10, 5.0, 35.0, 12.0),
            (20, 12.0, 80.0, -8.0),
        ):
            cmds.setKeyframe(hips, attribute="translateX", time=frame, value=hips_x)
            cmds.setKeyframe(hips, attribute="rotateY", time=frame, value=hips_yaw)
            cmds.setKeyframe(spine, attribute="rotateX", time=frame, value=spine_pitch)
        cmds.currentTime(10, edit=True, update=True)
        cmds.select(marker, replace=True)

        mappings = (
            MocapJointMapping("Hips", "Root_M", True, True),
            MocapJointMapping("Spine", "Spine1_M"),
            MocapJointMapping("Chest", "Chest_M"),
            MocapJointMapping("Neck", "Neck_M"),
            MocapJointMapping("Head", "Head_M"),
        )
        host = MayaMocapConnectionHost()
        selection = tuple(cmds.ls(selection=True, long=True) or [])
        initial_pose = tuple(cmds.xform("|Root_M", query=True, worldSpace=True, matrix=True))
        source_before = host.capture_mocap_source("|TakeA:Hips")

        connected = ConnectMocapBody(host).execute("|TakeA:Hips", mappings)
        pose_after_connect = tuple(cmds.xform("|Root_M", query=True, worldSpace=True, matrix=True))
        constraint_names = tuple(item.name for item in connected.plan.constraints)
        inputs_connected = all(
            state.source_node == spec.name
            for spec in connected.plan.constraints
            for state in host.capture_mocap_target_inputs(connected.plan)
            if state.target_path == spec.target_path
            and state.attribute in spec.target_attributes
        )

        cmds.undoInfo(stateWithoutFlush=False)
        try:
            cmds.currentTime(20, edit=True, update=True)
        finally:
            cmds.undoInfo(stateWithoutFlush=True)
        driven_pose = tuple(cmds.xform("|Root_M", query=True, worldSpace=True, matrix=True))
        driven_delta = max(abs(a - b) for a, b in zip(pose_after_connect, driven_pose))
        DisconnectMocapBody(host).execute("|TakeA:Hips", mappings)
        disconnected = not any(cmds.ls(name) for name in constraint_names)
        inputs_free = all(
            state.source_node is None
            for state in host.capture_mocap_target_inputs(connected.plan)
        )

        cmds.undo()
        undo_disconnect_restored = all(
            len(cmds.ls(name) or []) == 1 for name in constraint_names
        )
        cmds.undo()
        undo_connect_removed = not any(cmds.ls(name) for name in constraint_names)
        source_after = host.capture_mocap_source("|TakeA:Hips")

        checks = {
            "owned_body_detected": len(body.joints) == 30,
            "five_constraints_created": len(connected.snapshot.constraints) == 5,
            "root_parent_descendants_orient": (
                connected.plan.constraints[0].kind.value == "parentConstraint"
                and all(
                    item.kind.value == "orientConstraint"
                    for item in connected.plan.constraints[1:]
                )
            ),
            "maintain_offset_preserved_pose": max(
                abs(a - b) for a, b in zip(initial_pose, pose_after_connect)
            ) < 1e-5,
            "target_inputs_owned": inputs_connected,
            "animation_drives_body": driven_delta > 1e-3,
            "disconnect_removed_constraints": disconnected,
            "disconnect_released_inputs": inputs_free,
            "undo_disconnect_restored": undo_disconnect_restored,
            "undo_connect_removed": undo_connect_removed,
            "source_unchanged": source_after == source_before,
            "selection_preserved": tuple(
                cmds.ls(selection=True, long=True) or []
            ) == selection,
            "time_preserved_by_operations": abs(
                float(cmds.currentTime(query=True)) - 20.0
            ) < 1e-9,
        }

        cmds.file(new=True, force=True)
        checks["scene_cleanup"] = not (
            cmds.ls("Root_M", "FitSkeleton", "TakeA:*", long=True) or []
        )
        passed = all(checks.values())
        result = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "mocap_body_connection",
            **checks,
            "constraint_count": len(constraint_names),
            "driven_matrix_delta": driven_delta,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
