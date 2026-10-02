"""ADV 6.925 Skeleton geometry source-to-joint plan."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoneCopy:
    source: str
    joint: str
    side: str
    child: str = ""
    name: str = ""

    @property
    def target(self) -> str:
        return self.name or self.source + "Bone" + self.side

    @property
    def template(self) -> str:
        return self.source + "Bone"

    @property
    def skin_name(self) -> str:
        if self.source in {"Phalanges", "Metacarpal", "Generic", "horseCoffin"}:
            return self.target[:-2] + "BoneSC" + self.side
        return self.source + "BoneSC" + self.side


# The order matches asCreateSkeleton: later bones may use earlier landmarks.
_BONES = (
    ("Pelvis", "Root", ""), ("Cranium", "Head", "HeadEnd"),
    ("SpineVertebras", "Root", ""), ("Mandible", "Jaw", "HeadEnd"),
    ("Femur", "Hip", "Knee"), ("Tibia", "Knee", "Ankle"),
    ("Fibula", "Knee", "Ankle"), ("Calcaneus", "Ankle", ""),
    ("Talus", "Ankle", ""), ("Metatarsals", "Toes", ""),
    ("Phalanxs", "Toes", ""), ("Ribs", "Chest", ""),
    ("Humerus", "Shoulder", "Elbow"), ("Scapula", "Scapula", ""),
    ("Clavicle", "Scapula", ""), ("Ulna", "Elbow", "Wrist"),
    ("Radius", "Elbow", "Wrist"), ("CarpalA", "Wrist", "MiddleFinger1"),
    ("CarpalB", "Wrist", "MiddleFinger1"), ("Eye", "Eye", ""),
)
_QUADRUPED_EXCLUDE = frozenset({
    "Clavicle", "CarpalA", "CarpalB", "Calcaneus", "Talus",
    "Metatarsals", "Phalanxs",
})


def plan_skeleton_bones(joints: set[str] | frozenset[str],
                        fit_template: str = "") -> tuple[BoneCopy, ...]:
    """Select the named template pieces present in a Body DeformSet."""
    result: list[BoneCopy] = []
    for source, joint_stem, child_stem in _BONES:
        if fit_template in {"horse", "cat"} and source in _QUADRUPED_EXCLUDE:
            continue
        for side in ("_M", "_L", "_R"):
            joint = joint_stem + side
            if joint not in joints:
                continue
            child = child_stem + side if child_stem else ""
            result.append(BoneCopy(source, joint, side, child))
    return tuple(result)


def plan_finger_bones(joints: set[str] | frozenset[str],
                      fit_template: str = "") -> tuple[BoneCopy, ...]:
    if fit_template in {"horse", "cat"}:
        return ()
    result = []
    for joint in sorted(joints):
        if "Finger" not in joint or not joint.endswith(("_M", "_L", "_R")):
            continue
        stem, side = joint.rsplit("_", 1)
        result.append(BoneCopy("Phalanges", joint, "_" + side,
                               name=stem + "Bone_" + side))
    return tuple(result)


def plan_skeleton_mirror(names: set[str], source_side: str
                         ) -> tuple[tuple[str, str], ...]:
    """Pair original SkeletonGeometry bone names across the X mirror plane."""
    if source_side not in {"L", "R"}:
        raise ValueError("骨骼几何镜像来源侧必须是 L 或 R")
    target_side = "R" if source_side == "L" else "L"
    suffix = "_" + source_side
    return tuple((name, name[:-2] + "_" + target_side)
                 for name in sorted(names) if name.endswith(suffix)
                 and name[:-2] + "_" + target_side in names)


def plan_metacarpal_bones(joints: set[str] | frozenset[str],
                          fit_template: str = "") -> tuple[BoneCopy, ...]:
    result = []
    for joint in sorted(joints):
        if ("Finger1" not in joint or "ThumbFinger1" in joint
                or not joint.endswith(("_M", "_L", "_R"))):
            continue
        stem, side = joint.rsplit("_", 1)
        result.append(BoneCopy("Metacarpal", joint, "_" + side,
                               name=stem + "MetacarpalBone_" + side))
    return tuple(result)


def plan_generic_bones(joints: set[str] | frozenset[str],
                       named: tuple[BoneCopy, ...],
                       fit_template: str = "") -> tuple[BoneCopy, ...]:
    """Cover each remaining DeformSet joint with a real GenericBone mesh."""
    covered = {spec.joint for spec in named}
    result = []
    for joint in sorted(joints - covered):
        if not joint.endswith(("_M", "_L", "_R")):
            continue
        stem, side = joint.rsplit("_", 1)
        if fit_template == "cat" and stem == "Toes1":
            continue
        if (fit_template == "horse" and
                stem.endswith(("Fingers3", "Toes3"))):
            continue
        result.append(BoneCopy("Generic", joint, "_" + side,
                               name=stem + "Bone_" + side))
    return tuple(result)


def plan_horse_coffin_bones(joints: set[str] | frozenset[str],
                            fit_template: str) -> tuple[BoneCopy, ...]:
    if fit_template != "horse":
        return ()
    result = []
    for joint in sorted(joints):
        if not joint.endswith(("_M", "_L", "_R")):
            continue
        stem, side = joint.rsplit("_", 1)
        if stem.endswith(("Fingers3", "Toes3")):
            result.append(BoneCopy("horseCoffin", joint, "_" + side,
                                   name=stem + "Bone_" + side))
    return tuple(result)
