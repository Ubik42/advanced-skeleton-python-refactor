"""Native asRobloxDynamicHead frame layout, source MEL 25629–25670."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RobloxHeadFrame:
    attribute: str
    label: str


@dataclass(frozen=True)
class RobloxHeadKey:
    channel: str
    frame: int
    value: int


@dataclass(frozen=True)
class RobloxHeadExportPlan:
    channels: tuple[str, ...]
    frames: tuple[RobloxHeadFrame, ...]
    keys: tuple[RobloxHeadKey, ...]
    playback_end: int
    current_frame: int = 39


def plan_roblox_head_export(channels):
    # Preserve listAttr -ud -s order; the frame labels are derived from that
    # order, rather than the fixed 50-channel construction catalogue.
    channels = tuple(channels)
    frames = [RobloxHeadFrame('Frame0', 'Neutral')]
    keys = []
    for index, channel in enumerate(channels):
        keys.extend(RobloxHeadKey(channel, frame, value) for frame, value in (
            (index, 0), (index + 1, 10), (index + 2, 0)))
        frames.append(RobloxHeadFrame('Frame' + str(index + 1), channel))
    return RobloxHeadExportPlan(channels, tuple(frames), tuple(keys), len(channels))
