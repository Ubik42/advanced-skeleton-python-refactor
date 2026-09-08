from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def close(left, right, tolerance=1e-4):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def frame_close(left, right, tolerance=1e-4):
    return all(close(a, b, tolerance) for a, b in zip(left, right))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BakeBodyExportSkeleton,
            BuildBodyExportSkeleton,
            BuildBodyRootMotion,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
        )
        from adv_py.core import (
            BODY_EXPORT_CHANNEL_ATTRIBUTES,
            audit_body_export_skeleton,
            audit_body_root_motion,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="ExportSkeletonBakeSelection",
            skipSelect=True,
        )
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply("FitSkeleton").state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        body = BuildOrientedBodySkeleton(host).apply(container).snapshot
        root = body.root
        shoulder = "|Root_M|Spine1_M|Chest_M|Scapula_R|Shoulder_R"
        for frame, translation, yaw, shoulder_x in (
            (1, (0.0, 0.0, 8.0), 0.0, 0.0),
            (3, (4.0, 6.0, 12.0), 30.0, 20.0),
            (5, (8.0, 12.0, 16.0), 60.0, 40.0),
        ):
            for axis, value in zip("XYZ", translation):
                cmds.setKeyframe(
                    root,
                    attribute=f"translate{axis}",
                    time=frame,
                    value=value,
                )
            cmds.setKeyframe(
                root,
                attribute="rotateZ",
                time=frame,
                value=yaw,
            )
            cmds.setKeyframe(
                shoulder,
                attribute="rotateX",
                time=frame,
                value=shoulder_x,
            )
        source_key_counts = {
            plug: int(cmds.keyframe(plug, query=True, keyframeCount=True) or 0)
            for plug in (
                f"{root}.translateX",
                f"{root}.translateY",
                f"{root}.translateZ",
                f"{root}.rotateZ",
                f"{shoulder}.rotateX",
            )
        }
        cmds.currentTime(3, edit=True, update=True)
        cmds.select(marker, replace=True)

        root_motion = BuildBodyRootMotion(host).apply(
            source_container=container
        )
        export = BuildBodyExportSkeleton(host).apply(
            source_container=container
        )
        body_before_bake = host.capture_body_skeleton("Root_M")
        result = BakeBodyExportSkeleton(host).apply(
            start_frame=1,
            end_frame=5,
            source_container=container,
        )
        snapshot = result.verified
        checks = {
            "five_samples": len(result.samples) == 5,
            "thirty_baked_joints": len(snapshot.joints) == 30,
            "nine_channels_per_joint": all(
                len(state.channels) == len(BODY_EXPORT_CHANNEL_ATTRIBUTES) == 9
                for state in snapshot.joints
            ),
            "five_linear_keys_per_channel": all(
                len(channel.keys) == 5
                and all(
                    key.in_tangent == "linear"
                    and key.out_tangent == "linear"
                    for key in channel.keys
                )
                for state in snapshot.joints
                for channel in state.channels
            ),
            "root_motion_baked": (
                not snapshot.root_motion.point_constraint_exists
                and not snapshot.root_motion.orient_constraint_exists
                and all(
                    len(channel.keys) == 5
                    for channel in snapshot.root_motion.channels
                )
            ),
            "all_live_constraints_removed": not snapshot.root_constraint_exists,
            "all_source_messages_removed": not any(
                state.source_message_exists for state in snapshot.joints
            ),
            "bake_range_recorded": (
                snapshot.start_frame == 1
                and snapshot.end_frame == 5
                and snapshot.sample_by == 1
            ),
            "current_time_preserved": abs(
                float(cmds.currentTime(query=True)) - 3.0
            ) < 1e-6,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
            "body_preserved": result.body == body_before_bake,
            "source_animation_preserved": all(
                int(cmds.keyframe(plug, query=True, keyframeCount=True) or 0)
                == count
                for plug, count in source_key_counts.items()
            ),
        }

        export_nodes = {
            state.output_path for state in snapshot.joints
        } | {snapshot.root_motion.output_path}
        cross_dependencies = []
        for joint in body.joints:
            connections = cmds.listConnections(
                joint.path,
                source=True,
                destination=True,
            ) or []
            for node in connections:
                paths = cmds.ls(node, long=True) or [node]
                if any(path in export_nodes for path in paths):
                    cross_dependencies.append((joint.path, paths[0]))
        checks["no_body_export_dependencies"] = not cross_dependencies

        cmds.undoInfo(stateWithoutFlush=False)
        playback_matches = True
        try:
            for frame in range(1, 6):
                cmds.currentTime(frame, edit=True, update=True)
                body_state = host.capture_body_skeleton("Root_M")
                export_states = {
                    spec.source_path: spec.output_path
                    for spec in result.plan.bake.export_skeleton.joints
                }
                body_by_path = {state.path: state for state in body_state.joints}
                for source_path, output_path in export_states.items():
                    position = cmds.xform(
                        output_path,
                        query=True,
                        worldSpace=True,
                        translation=True,
                    )
                    matrix = cmds.xform(
                        output_path,
                        query=True,
                        worldSpace=True,
                        matrix=True,
                    )
                    axes = tuple(
                        host._normalized_vector(tuple(
                            float(value) for value in matrix[index:index + 3]
                        ))
                        for index in (0, 4, 8)
                    )
                    source_state = body_by_path[source_path]
                    playback_matches = playback_matches and close(
                        position,
                        source_state.world_position,
                    ) and frame_close(axes, source_state.world_axes)
        finally:
            cmds.currentTime(3, edit=True, update=True)
            cmds.undoInfo(stateWithoutFlush=True)
        checks["independent_playback_matches_body"] = playback_matches

        cmds.undo()
        restored_root_motion = host.capture_body_root_motion(
            root_motion.plan.root_motion
        )
        restored_export = host.capture_body_export_skeleton(
            export.plan.export_skeleton
        )
        checks["single_undo_restored_live_root_motion"] = not (
            audit_body_root_motion(
                root_motion.plan.root_motion,
                restored_root_motion,
            )
        )
        checks["single_undo_restored_live_export_skeleton"] = not (
            audit_body_export_skeleton(
                export.plan.export_skeleton,
                restored_export,
            )
        )

        cmds.undo()
        checks["second_undo_removed_export_skeleton"] = not (
            cmds.ls("AdvPy_EXP_*", long=True) or []
        )
        cmds.undo()
        checks["third_undo_removed_root_motion"] = not any(
            cmds.ls(name, long=True) or []
            for name in root_motion.plan.root_motion.node_names
        )
        cmds.delete("|Root_M", container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
            "AdvPy_EXP_*",
            "AdvPy_GameRootMotion*",
            marker,
            long=True,
        ) or []
        checks["cleanup"] = not remaining

        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_game_export_skeleton_bake",
            **checks,
            "source_joint_count": len(body.joints),
            "export_joint_count": len(snapshot.joints),
            "sample_count": len(result.samples),
            "cross_dependencies": cross_dependencies,
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
