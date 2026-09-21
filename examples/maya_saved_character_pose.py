"""Capture / restore the registered character in an already opened Maya scene.

The functions create a fresh host and resolve scene registration every time;
no object returned by character construction is required.
"""
from adv_py.adapters import MayaBodyBuildHost
from adv_py.application import (
    CaptureBodyCharacterPose, ApplyBodyCharacterPose,
    save_character_pose, load_character_pose,
)


def capture_to_file(destination):
    pose=CaptureBodyCharacterPose(MayaBodyBuildHost()).execute()
    return save_character_pose(pose,destination)


def restore_from_file(source):
    return ApplyBodyCharacterPose(MayaBodyBuildHost()).apply(load_character_pose(source))
