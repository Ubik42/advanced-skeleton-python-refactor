"""Call from an initialized Maya session containing one registered character."""
from adv_py.adapters import MayaBodyBuildHost
from adv_py.application import (
    CaptureBodyCharacterAnimation, ApplyBodyCharacterAnimation, BakeBodyCharacterSpineMode,
    save_character_animation, load_character_animation,
)


def capture_to_file(destination,start,end,step=1):
    clip=CaptureBodyCharacterAnimation(MayaBodyBuildHost()).execute(start,end,step)
    return save_character_animation(clip,destination)


def restore_from_file(source):
    return ApplyBodyCharacterAnimation(MayaBodyBuildHost()).apply(load_character_animation(source))


def convert_spine(start,end,mode,step=1):
    return BakeBodyCharacterSpineMode(MayaBodyBuildHost()).execute(start,end,mode,step)
