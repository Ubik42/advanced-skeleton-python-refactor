"""Exercise panel animation editing against a generated registered character."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(report: Path) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.application import (BuildRegisteredBodyCharacter,
            BuildSyntheticBodySourceFit, CreateFitSkeleton)
        from adv_py.core.body_control_spaces import control_space_pose_error
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cmds.upAxis(axis="z", rotateView=False)
        cmds.undoInfo(state=True)
        host = MayaFaceHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        built = BuildRegisteredBodyCharacter(host).apply(container)
        controller = MayaPanelController()
        limb_channels = controller.animation_enable_limb(":")
        stretch_channels = controller.animation_enable_stretch(":")
        space_channels = controller.animation_enable_spaces(":")
        registration = host.read_character_registration()
        cmds.currentTime(1)
        first_keyed = controller.animation_key_current(":")
        global_x = next(channel for channel in registration.channels
                        if channel.key == "global.translateX")
        cmds.setKeyframe(global_x.node, attribute=global_x.attribute,
                         time=3, value=2.)
        cmds.currentTime(3)
        third_keyed = controller.animation_key_current(":")
        frames = (1., 2., 3.)

        def body_samples():
            samples = host.sample_character_animation(registration, frames)
            return tuple(pose.body_frames for _, pose in samples)

        before = body_samples()
        limb_frames = controller.animation_bake_limb(":", 1, 3,
            "arm", "R", "ik", 1)
        after_limb = body_samples()
        spine_frames = controller.animation_bake_spine(":", 1, 3, "ik", 1)
        after_spine = body_samples()
        before_space = host.sample_character_animation(registration, (2.,))[0][1]
        old_keys = host.capture_character_key_state(registration)
        mode = controller.animation_switch_space(":", "hand_R", "body", 2)
        after_space = host.sample_character_animation(registration, (2.,))[0][1]
        changed_keys = host.capture_character_key_state(registration)
        cmds.undo()
        undone_keys = host.capture_character_key_state(registration)
        cmds.redo()
        redone_keys = host.capture_character_key_state(registration)

        def largest_pose_error(left, right):
            return max(control_space_pose_error(a, b) for a, b in zip(left, right))

        checks = {
            "registered_character": len(built.registration.body) == 30,
            "limb_channels_enabled": limb_channels > len(built.registration.channels),
            "stretch_channels_enabled": stretch_channels >= limb_channels,
            "space_channels_enabled": space_channels > stretch_channels,
            "whole_pose_keyed": first_keyed == space_channels
                and third_keyed == space_channels,
            "limb_range_baked": limb_frames == 3
                and largest_pose_error(before, after_limb) < 1e-4,
            "spine_range_baked": spine_frames == 3
                and largest_pose_error(after_limb, after_spine) < 1e-4,
            "space_switch_preserves_body": mode == "body"
                and control_space_pose_error(before_space.body_frames,
                                             after_space.body_frames) < 1e-4,
            "space_switch_single_undo": undone_keys == old_keys,
            "space_switch_redo": redone_keys == changed_keys,
        }
        payload = {**checks, "status": "passed" if all(checks.values()) else "failed",
                   "channel_count": space_channels}
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
