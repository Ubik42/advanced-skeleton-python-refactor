"""Intermediate Skin influences at the final segment of each finger."""
from __future__ import annotations

from dataclasses import dataclass

from .body_skeleton import BodySkeletonSnapshot


@dataclass(frozen=True, slots=True)
class FingerMidSpec:
    name: str
    path: str
    zero_name: str
    zero_path: str
    parent: str
    tip: str
    position: tuple[float, float, float]


def plan_finger_mid_influences(body: BodySkeletonSnapshot) -> tuple[FingerMidSpec, ...]:
    by_name = {joint.name: joint for joint in body.joints}
    if len(by_name) != len(body.joints):
        raise ValueError("Body 关节名称不唯一")
    original = {f"{finger}Finger{index}_{side}"
                for side in ("R", "L")
                for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky")
                for index in (2, 3)}
    canonical = {f"{finger}{index}_{side}"
                 for side in ("R", "L")
                 for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky")
                 for index in (2, 3)}
    if original <= by_name.keys():
        finger_marker = "Finger"
    elif canonical <= by_name.keys():
        finger_marker = ""
    else:
        raise ValueError("手指末段需要完整的双侧五指 Body 链")
    specs = []
    for side in ("R", "L"):
        for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
            stem = f"{finger}{finger_marker}3_{side}"
            tip = by_name.get(stem)
            parent = by_name.get(f"{finger}{finger_marker}2_{side}")
            if tip is None or parent is None or tip.parent_path != parent.path:
                raise ValueError("手指末段需要 Finger2 → Finger3 直接父子链：" + stem)
            name = stem + "_50"
            zero_name = stem + "_00"
            specs.append(FingerMidSpec(name, parent.path + "|" + name,
                                       zero_name, parent.path + "|" + zero_name,
                                       parent.path, tip.path, tip.world_position))
    return tuple(specs)
