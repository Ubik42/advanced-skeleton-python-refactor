"""ADV Body / Unreal Joints: generic IK marker hierarchy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


IK_MARKERS = (
    ("ik_foot_root", "<root>", None),
    ("ik_foot_l", "ik_foot_root", "Ankle_L"),
    ("ik_foot_r", "ik_foot_root", "Ankle_R"),
    ("ik_hand_root", "<root>", None),
    ("ik_hand_gun", "ik_hand_root", "Wrist_R"),
    ("ik_hand_l", "ik_hand_root", "Wrist_L"),
    ("ik_hand_r", "ik_hand_gun", None),
)


@dataclass(frozen=True, slots=True)
class UnrealJointSpec:
    name: str
    parent: str
    align_to: str | None


@dataclass(frozen=True, slots=True)
class UnrealJointPlan:
    create_root: bool
    root: str
    opm: bool
    joints: tuple[UnrealJointSpec, ...]


def plan_unreal_joints(*, has_root_motion: bool, opm: bool,
                       landmarks: Mapping[str, bool]) -> UnrealJointPlan:
    if not isinstance(has_root_motion, bool) or not isinstance(opm, bool):
        raise ValueError("Unreal Joints 角色选项须为布尔值")
    root = "root" if has_root_motion else "UnrealRoot"
    specs = tuple(UnrealJointSpec(name, root if parent == "<root>" else parent,
                                  source if source and landmarks.get(source)
                                  else None)
                  for name, parent, source in IK_MARKERS)
    return UnrealJointPlan(not has_root_motion, root, opm, specs)
