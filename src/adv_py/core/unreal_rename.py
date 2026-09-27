"""Pure name mapping for ADV's rename-to-Unreal export path."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class UnrealRenamePlan:
    names: tuple[tuple[str, str], ...]
    spine: tuple[str, ...]
    twist_families: tuple[str, ...] = ("thigh", "calf", "upperarm", "lowerarm")


def plan_unreal_rename(joints: Iterable[str], spine_between_root_and_chest:
                       Iterable[str]) -> UnrealRenamePlan:
    present = set(joints)
    if "Root_M" not in present or "Chest_M" not in present:
        raise ValueError("Unreal 重命名需要 Root_M 与 Chest_M")
    mapping = {
        "Root_M": "pelvis", "Neck_M": "neck_01", "Head_M": "head",
    }
    side_map = {
        "Hip": "thigh", "Knee": "calf", "Ankle": "foot",
        "Toes": "ball", "Scapula": "clavicle", "Shoulder": "upperarm",
        "Elbow": "lowerarm", "Wrist": "hand",
    }
    for side in ("R", "L"):
        suffix = "_" + side
        ue = "_" + side.lower()
        last_knee = max((index for index in range(1, 10)
                         if f"KneePart{index}{suffix}" in present), default=0)
        last_elbow = max((index for index in range(1, 10)
                          if f"ElbowPart{index}{suffix}" in present), default=0)
        for adv, target in side_map.items():
            mapping[adv + suffix] = target + ue
        for index in range(1, 10):
            for adv, target in (("Hip", "thigh"), ("Knee", "calf"),
                                ("Shoulder", "upperarm"),
                                ("Elbow", "lowerarm")):
                numbered = (last_knee - index + 1 if adv == "Knee" else
                            last_elbow - index + 1 if adv == "Elbow" else index)
                mapping[f"{adv}Part{index}{suffix}"] = (
                    f"{target}_twist_{numbered:02d}{ue}")
        for digit in ("Index", "Middle", "Ring", "Pinky", "Thumb"):
            mapping[f"{digit}Finger0{suffix}"] = (
                f"{digit.lower()}_metacarpal{ue}")
            for index in (1, 2, 3):
                mapping[f"{digit}Finger{index}{suffix}"] = (
                    f"{digit.lower()}_{index:02d}{ue}")
    for index in range(1, 10):
        mapping[f"NeckPart{index}_M"] = f"neck_{index + 1:02d}"
    spine = tuple(spine_between_root_and_chest)
    if not spine or spine[-1] != "Chest_M":
        raise ValueError("Chest_M 不在 Root_M 的脊柱链上")
    for index, name in enumerate(spine, 1):
        mapping[name] = f"spine_{index:02d}"
    for name in present:
        if name in mapping:
            continue
        if name.endswith(("_R", "_L")):
            mapping[name] = name[:-1] + name[-1].lower()
        elif name.endswith("_M"):
            mapping[name] = name[:-2]
    selected = tuple(sorted(((name, target) for name, target in mapping.items()
                             if name in present), key=lambda pair: pair[0]))
    targets = [target for _, target in selected]
    if len(targets) != len(set(targets)):
        raise ValueError("ADV 关节映射会产生重复的 Unreal 名称")
    return UnrealRenamePlan(selected, spine)
