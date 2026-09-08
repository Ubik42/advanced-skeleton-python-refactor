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


def key_count(cmds, plug):
    return int(cmds.keyframe(plug, query=True, keyframeCount=True) or 0)


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import BakeBodyRootMotion, BuildBodyRootMotion
        from adv_py.core import (
            audit_body_root_motion,
            oriented_body_provenance,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="RootMotionBakeSelection",
            skipSelect=True,
        )
        container = cmds.createNode(
            "transform",
            name="FitSkeleton",
            skipSelect=True,
        )
        root = cmds.createNode("joint", name="Root_M", skipSelect=True)
        host = MayaBodyBuildHost()
        with host.transaction("创建 Root Motion bake 自生成 Body"):
            host.write_body_provenance(
                "|Root_M",
                oriented_body_provenance("|FitSkeleton", 1),
            )

        frames = (1, 3, 5)
        translations = (
            (0.0, 0.0, 10.0),
            (4.0, 6.0, 20.0),
            (8.0, 12.0, 30.0),
        )
        rotations = (
            (5.0, 0.0, 0.0),
            (0.0, 0.0, 30.0),
            (-5.0, 0.0, 60.0),
        )
        for frame, translation, rotation in zip(frames, translations, rotations):
            for axis, value in zip("XYZ", translation):
                cmds.setKeyframe(
                    root,
                    attribute=f"translate{axis}",
                    time=frame,
                    value=value,
                )
            for axis, value in zip("XYZ", rotation):
                cmds.setKeyframe(
                    root,
                    attribute=f"rotate{axis}",
                    time=frame,
                    value=value,
                )
        source_key_counts = {
            attribute: key_count(cmds, f"{root}.{attribute}")
            for kind in ("translate", "rotate")
            for axis in "XYZ"
            for attribute in (f"{kind}{axis}",)
        }
        cmds.currentTime(3, edit=True, update=True)
        cmds.select(marker, replace=True)

        built = BuildBodyRootMotion(host).apply(source_container="|FitSkeleton")
        body_before_bake = host.capture_body_skeleton("Root_M")
        baked = BakeBodyRootMotion(host).apply(
            start_frame=1,
            end_frame=5,
            source_container="|FitSkeleton",
        )
        plan = baked.plan.bake
        channels = {state.attribute: state for state in baked.verified.channels}
        checks = {
            "sampled_every_integer_frame": tuple(
                sample.frame for sample in baked.samples
            ) == (1, 2, 3, 4, 5),
            "three_export_channels": set(channels) == {
                "translateX",
                "translateY",
                "rotateZ",
            },
            "five_keys_per_channel": all(
                len(state.keys) == 5 for state in channels.values()
            ),
            "all_keys_linear": all(
                key.in_tangent == "linear" and key.out_tangent == "linear"
                for state in channels.values()
                for key in state.keys
            ),
            "constraints_removed": (
                not baked.verified.point_constraint_exists
                and not baked.verified.orient_constraint_exists
            ),
            "current_time_preserved": abs(
                float(cmds.currentTime(query=True)) - 3.0
            ) < 1e-6,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
            "body_preserved": baked.body == body_before_bake,
        }

        cmds.undoInfo(stateWithoutFlush=False)
        playback_matches_samples = True
        try:
            for sample in baked.samples:
                cmds.currentTime(sample.frame, edit=True, update=True)
                translation = cmds.getAttr(
                    f"{plan.root_motion.output_path}.translate"
                )[0]
                rotation = cmds.getAttr(
                    f"{plan.root_motion.output_path}.rotate"
                )[0]
                playback_matches_samples = playback_matches_samples and close(
                    translation,
                    sample.translation,
                ) and close(rotation, sample.rotation)
        finally:
            cmds.currentTime(3, edit=True, update=True)
            cmds.undoInfo(stateWithoutFlush=True)
        checks["baked_playback_matches_samples"] = playback_matches_samples

        cmds.undo()
        restored = host.capture_body_root_motion(built.plan.root_motion)
        checks["single_undo_restored_live_driver"] = not audit_body_root_motion(
            built.plan.root_motion,
            restored,
        )
        checks["single_undo_preserved_source_animation"] = all(
            key_count(cmds, f"{root}.{attribute}") == count
            for attribute, count in source_key_counts.items()
        )
        checks["single_undo_kept_body_and_fit"] = (
            cmds.objExists(root) and cmds.objExists(container)
        )

        cmds.undo()
        checks["second_undo_removed_root_motion"] = not any(
            cmds.ls(name, long=True) or []
            for name in built.plan.root_motion.node_names
        )
        cmds.delete(root, container, marker)
        remaining = cmds.ls(
            "Root_M",
            "FitSkeleton",
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
            "slice": "body_game_root_motion_bake",
            **checks,
            "start_frame": plan.start_frame,
            "end_frame": plan.end_frame,
            "sample_count": len(baked.samples),
            "channel_count": len(channels),
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
