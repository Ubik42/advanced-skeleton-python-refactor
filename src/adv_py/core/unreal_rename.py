"""Pure name mapping for ADV's rename-to-Unreal export path."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class UnrealRenamePlan:
    names: tuple[tuple[str, str], ...]
    spine: tuple[str, ...]
    twist_families: tuple[str, ...] = ("thigh", "calf", "upperarm", "lowerarm")
    right_knee_parts: int = 0
    right_elbow_parts: int = 0
    known_names: tuple[str, ...] = ()


def plan_unreal_rename(joints: Iterable[str], spine_between_root_and_chest:
                       Iterable[str]) -> UnrealRenamePlan:
    original = tuple(joints)
    present = set(original)
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
    # The MEL counts only the right side, then mirrors that same name table.
    last_knee = max((index for index in range(1, 10)
                     if f"KneePart{index}_R" in present), default=0)
    last_elbow = max((index for index in range(1, 10)
                      if f"ElbowPart{index}_R" in present), default=0)
    for side in ("R", "L"):
        suffix = "_" + side
        ue = "_" + side.lower()
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
    known = ['Root_M', 'Hip_R', 'Knee_R', 'Ankle_R', 'Toes_R',
             'Scapula_R', 'Shoulder_R', 'Elbow_R', 'Wrist_R', 'Neck_M', 'Head_M']
    for index in range(1, 10):
        known.extend((f'HipPart{index}_R', f'KneePart{index}_R',
                      f'ShoulderPart{index}_R', f'ElbowPart{index}_R', f'NeckPart{index}_M'))
    for index in (1, 2, 3):
        known.extend(f'{digit}Finger{index}_R' for digit in ('Index', 'Middle', 'Ring', 'Pinky', 'Thumb'))
    known.extend(f'{digit}Finger0_R' for digit in ('Index', 'Middle', 'Ring', 'Pinky', 'Thumb'))
    known.extend(name.replace('_R', '_L', 1) for name in tuple(known) if name.endswith('_R'))
    known = tuple(name for name in known if name in present)
    order = tuple(dict.fromkeys((*spine, *known, *original)))
    selected = tuple((name, mapping[name]) for name in order if name in mapping and name in present)
    return UnrealRenamePlan(selected, spine, right_knee_parts=last_knee,
                           right_elbow_parts=last_elbow, known_names=known)


def unknown_unreal_name(name: str) -> str | None:
    if name.endswith(('_R', '_L')):
        return name[:-1] + name[-1].lower()
    if name.endswith('_M'):
        return name[:-2]
    return None
