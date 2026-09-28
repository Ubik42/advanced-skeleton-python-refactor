"""Animator channels created by the Fit Part twist graph."""
from __future__ import annotations

from .character_registry import CharacterChannel
from .fit_part import FitPartFinalPaths
from .fit_part_twist import FitPartTwistStep


def plan_fit_part_animation_channels(
    steps: tuple[FitPartTwistStep, ...],
    paths: FitPartFinalPaths,
) -> tuple[CharacterChannel, ...]:
    part_paths = dict(paths.part_paths)
    body_paths = dict(paths.body_paths)
    if (len(part_paths) != len(paths.part_paths)
            or len(body_paths) != len(paths.body_paths)):
        raise ValueError("Fit Part 动画登记路径重复")
    channels = []
    for step in steps:
        part = part_paths.get(step.part_name)
        if part is None:
            raise ValueError("Fit Part 动画登记缺少分段关节："
                             + step.part_name)
        channels.extend((
            CharacterChannel("fitpart." + step.part_name
                             + ".twistAmount", part, "twistAmount",
                             0.0, 1.0),
            CharacterChannel("fitpart." + step.part_name
                             + ".twistAddition", part, "twistAddition"),
        ))
        if step.compensate_start_body:
            name = step.start_body.rsplit("|", 1)[-1]
            body = body_paths.get(name)
            if body is None or body != paths.remap_body_reference(
                    step.start_body):
                raise ValueError("Fit Part 动画登记缺少起点 Body：" + name)
            channels.extend((
                CharacterChannel("fitpart." + name + ".twistAmount",
                                 body, "twistAmount", 0.0, 1.0),
                CharacterChannel("fitpart." + name + ".twistAddition",
                                 body, "twistAddition"),
            ))
    if (len({channel.key for channel in channels}) != len(channels)
            or len({(channel.node, channel.attribute)
                    for channel in channels}) != len(channels)):
        raise ValueError("Fit Part 动画登记通道重复")
    return tuple(channels)
