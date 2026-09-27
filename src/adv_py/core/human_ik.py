"""AdvancedSkeleton 6.925 HumanIK definition and bake selection plans."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class HumanIkAssignment:
    slot: str
    source: str


@dataclass(frozen=True, slots=True)
class HumanIkDefinitionPlan:
    assignments: tuple[HumanIkAssignment, ...]
    create_control_rig: bool


@dataclass(frozen=True, slots=True)
class HumanIkBakePlan:
    first_frame: float
    last_frame: float
    controls: tuple[str, ...]
    drivers: tuple[tuple[str, str, str], ...]


def plan_human_ik_definition(
        available: frozenset[str], *,
        create_control_rig: bool = True) -> HumanIkDefinitionPlan:
    if "Root_M" not in available:
        raise ValueError("HumanIK 缺少 Root_M")
    if not isinstance(create_control_rig, bool):
        raise ValueError("HumanIK 控制绑定选项须为布尔值")
    entries = [("Hips", "Root_M")]
    if "RootPart1_M" in available:
        entries.extend((
            ("Spine", "RootPart1_M"),
            ("Spine1", "RootPart2_M"),
            ("Spine2", "Spine1_M"),
            ("Spine3", "Spine1Part1_M"),
            ("Spine4", "Spine1Part2_M"),
            ("Spine5", "Chest_M"),
        ))
    else:
        entries.append(("Spine", "Spine1_M"))
        spine_index = 2
        while "Spine%d_M" % spine_index in available:
            entries.append(("Spine%d" % (spine_index - 1),
                            "Spine%d_M" % spine_index))
            spine_index += 1
        entries.append(("Spine%d" % (spine_index - 1), "Chest_M"))
    entries.extend((("Neck", "FKNeck_M"), ("Head", "FKHead_M")))
    for side, suffix in (("Right", "_R"), ("Left", "_L")):
        for slot, source in (
                ("UpLeg", "Hip"), ("Leg", "Knee"),
                ("Foot", "Ankle"), ("ToeBase", "Toes"),
                ("Shoulder", "Scapula"), ("Arm", "Shoulder"),
                ("ForeArm", "Elbow"), ("Hand", "Wrist")):
            entries.append((side + slot, source + suffix))
        for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
            for index in range(1, 5):
                entries.append((side + "Hand" + finger + str(index),
                                finger + "Finger" + str(index) + suffix))
        for index in range(1, 6):
            for slot, source in (
                    ("ArmRoll", "ShoulderPart"),
                    ("ForeArmRoll", "ElbowPart"),
                    ("UpLegRoll", "HipPart"),
                    ("LegRoll", "KneePart")):
                entries.append(("Leaf" + side + slot + str(index),
                                source + str(index) + suffix))
    assignments = tuple(HumanIkAssignment(slot, source)
                        for slot, source in entries if source in available)
    slots = [item.slot for item in assignments]
    if len(slots) != len(set(slots)):
        raise ValueError("HumanIK 槽位重复")
    return HumanIkDefinitionPlan(assignments, create_control_rig)


def plan_human_ik_bake(
        available: frozenset[str], first_frame: float,
        last_frame: float) -> HumanIkBakePlan:
    if ("Root_M" not in available or "RootX_M" not in available
            or not isfinite(first_frame) or not isfinite(last_frame)
            or first_frame > last_frame):
        raise ValueError("HumanIK Bake 缺少 Body 根或有效帧范围")
    middle = ("RootX", "FKSpine1", "FKSpine2", "FKChest", "FKNeck",
              "FKHead", "IKSpine1", "IKSpine3")
    middle += tuple("FKSpine%d" % index for index in range(1, 21))
    sides = ("FKScapula", "FKShoulder", "FKElbow", "FKWrist",
             "FKHip", "FKKnee", "FKAnkle", "FKToes",
             "IKArm", "PoleArm", "IKLeg", "PoleLeg")
    fingers = tuple("FK%sFinger%d" % (finger, index)
                    for finger in ("Thumb", "Pinky", "Ring", "Middle",
                                   "Cup", "Index") for index in range(1, 4))
    controls = tuple(dict.fromkeys(
        [name + "_M" for name in middle if name + "_M" in available]
        + [name + side for name in sides + fingers
           for side in ("_R", "_L") if name + side in available]))
    # (source duplicate, destination control, constraint type)
    driver_names = [("Root_M", "RootX_M", "parentOffset")]
    driver_names.extend(("Spine%d_M" % index,
                         "FKSpine%d_M" % index, "parent")
                        for index in range(1, 21))
    driver_names.extend((source, target, "parent") for source, target in (
        ("Chest_M", "FKChest_M"), ("Neck_M", "FKNeck_M"),
        ("Head_M", "FKHead_M")))
    driver_names.extend((source, target, "parentOffset") for source, target in (
        ("Spine1_M", "IKSpine1_M"),
        ("Chest_M", "IKSpine3_M")))
    for side in ("_R", "_L"):
        for stem in ("Scapula", "Shoulder", "Elbow", "Wrist",
                     "Hip", "Knee", "Ankle", "Toes"):
            driver_names.append((stem + side, "FK" + stem + side, "parent"))
        driver_names.extend((
            ("Wrist" + side, "IKArm" + side, "parentOffset"),
            ("Elbow" + side, "PoleArm" + side, "point"),
            ("Ankle" + side, "IKLeg" + side, "parentOffset"),
            ("Knee" + side, "PoleLeg" + side, "point"),
        ))
        for finger in ("Thumb", "Pinky", "Ring", "Middle", "Cup", "Index"):
            for index in range(1, 4):
                stem = "%sFinger%d%s" % (finger, index, side)
                driver_names.append((stem, "FK" + stem, "parent"))
    drivers = tuple(("prefix_" + source, target, kind)
                    for source, target, kind in driver_names
                    if source in available and target in available)
    return HumanIkBakePlan(first_frame, last_frame, controls, drivers)
