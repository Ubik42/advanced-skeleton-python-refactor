"""Data-only correspondence between ADV deform joints and Unreal templates."""
from __future__ import annotations

from dataclasses import dataclass


TEMPLATES = {
    "Mannequin (UE4)": ("Mannequin", "SK_Mannequin_Skeleton"),
    "Manny (UE5)": ("Manny", "SK_Mannequin"),
    "Quinn (UE5)": ("Quinn", "SK_Mannequin"),
}


@dataclass(frozen=True, slots=True)
class JointMatch:
    source: str
    target: str
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    maintain_orientation: bool = False


@dataclass(frozen=True, slots=True)
class MannequinPlan:
    template: str
    top_node: str
    unreal_skeleton: str
    scale_adv_to_template: bool
    matches: tuple[JointMatch, ...]


def plan_mannequin(template: str = "Manny (UE5)", *,
                   scale_adv_to_template: bool = True) -> MannequinPlan:
    if template not in TEMPLATES:
        raise ValueError("未知 Unreal Mannequin 模板：" + template)
    if not isinstance(scale_adv_to_template, bool):
        raise ValueError("缩放选项须为布尔值")
    flip = (180.0, 0.0, 0.0)
    finger = (90.0, 0.0, 180.0)
    pairs = [
        JointMatch("Root_M", "pelvis", flip),
        JointMatch("Chest_M", "<last_spine>", flip),
        JointMatch("Neck_M", "neck_01", flip),
        JointMatch("NNeckPart1_M", "neck_02", flip),
        JointMatch("Head_M", "head", flip),
        JointMatch("hand_r", "ik_hand_gun", maintain_orientation=True),
    ]
    for side in ("R", "L"):
        ue = side.lower()
        arm = (
            ("Scapula", "clavicle", (180.0, 0.0, 180.0)),
            ("Shoulder", "upperarm", (0.0, -180.0, 0.0)),
            ("ShoulderPart1", "upperarm_twist_01", (0.0, -180.0, 0.0)),
            ("ShoulderPart2", "upperarm_twist_02", (0.0, -180.0, 0.0)),
            ("Elbow", "lowerarm", (180.0, 0.0, 180.0)),
            ("ElbowPart2", "lowerarm_twist_01", (0.0, -180.0, 0.0)),
            ("ElbowPart1", "lowerarm_twist_02", (0.0, -180.0, 0.0)),
            ("Wrist", "hand", finger),
            ("Hip", "thigh", (0.0, 0.0, 0.0)),
            ("HipPart1", "thigh_twist_01", (0.0, 0.0, 0.0)),
            ("HipPart2", "thigh_twist_02", (0.0, 0.0, 0.0)),
            ("Knee", "calf", (0.0, 0.0, 0.0)),
            ("KneePart2", "calf_twist_01", (0.0, 0.0, 0.0)),
            ("KneePart1", "calf_twist_02", (0.0, 0.0, 0.0)),
            ("Ankle", "foot", (0.0, 0.0, 0.0)),
            ("Toes", "ball", (0.0, 0.0, 0.0)),
        )
        pairs.extend(JointMatch(source + "_" + side, target + "_" + ue,
                                offset, target == "ball")
                     for source, target, offset in arm)
        for digit in ("Pinky", "Ring", "Middle", "Index"):
            pairs.append(JointMatch(digit + "Finger0_" + side,
                                    digit.lower() + "_metacarpal_" + ue,
                                    finger))
        for digit in ("Pinky", "Ring", "Middle", "Index", "Thumb"):
            for index in (1, 2, 3):
                pairs.append(JointMatch(f"{digit}Finger{index}_{side}",
                                        f"{digit.lower()}_0{index}_{ue}", finger))
        pairs.extend((
            JointMatch("foot_" + ue, "ik_foot_" + ue,
                       maintain_orientation=True),
            JointMatch("hand_" + ue, "ik_hand_" + ue,
                       maintain_orientation=True),
        ))
    top, skeleton = TEMPLATES[template]
    return MannequinPlan(template, top, skeleton, scale_adv_to_template,
                         tuple(pairs))
