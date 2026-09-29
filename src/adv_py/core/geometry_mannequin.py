"""Plan the 6.925 Mannequin template pieces for Body segments."""
from __future__ import annotations

from dataclasses import dataclass
from math import dist, isfinite


Vec3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class MannequinSegment:
    joint: str
    child: str
    start: Vec3
    end: Vec3


@dataclass(frozen=True, slots=True)
class MannequinPiece:
    joint: str
    child: str
    source: str
    name: str
    scale: Vec3
    start: Vec3
    end: Vec3


def plan_mannequin(segments: tuple[MannequinSegment, ...],
                   character_height: float) -> tuple[MannequinPiece, ...]:
    if not isfinite(character_height) or character_height <= 0:
        raise ValueError("Mannequin 角色高度无效")
    if not segments:
        raise ValueError("Mannequin 没有可用的 Body 骨段")
    pieces = []
    for segment in segments:
        joint = segment.joint
        length = dist(segment.start, segment.end)
        if (not joint.endswith(("_M", "_R", "_L"))
                or not segment.child or length < 1e-5):
            raise ValueError("Mannequin 骨段无效：" + joint)
        if "Part" in joint:
            continue
        stem = joint[:-2]
        axial = (joint == "Root_M" or stem.startswith("Spine")
                 or stem == "Chest" or stem.startswith("Head"))
        if axial:
            source = "Mannequin_Head" if stem.startswith("Head") else "Mannequin_Root"
            pieces.append(MannequinPiece(joint, segment.child, source,
                joint + "_Root", (length, character_height / 10,
                                  character_height / 10),
                segment.start, segment.end))
        if (joint in ("Root_M", "Chest_M", "Jaw_M")
                or stem.startswith(("Spine", "Head", "Eye"))):
            continue
        foot = stem.startswith(("Ankle", "Toes"))
        if foot:
            source, suffix = "Mannequin_Foot", "_Sphere"
            scale = (length, length, length)
        else:
            source, suffix = "Mannequin_Limb", "_Limb"
            scale = (length, length / 2, length / 2)
            if stem.startswith("Wrist"):
                scale = (scale[0], scale[1] * 3, scale[2])
            if stem.startswith("Finger"):
                scale = (length, character_height / 70,
                         character_height / 70)
            if stem.startswith("Neck"):
                scale = (length * 1.1, character_height / 10,
                         character_height / 10)
        pieces.append(MannequinPiece(joint, segment.child, source,
            joint + suffix, scale, segment.start, segment.end))
        sphere = length / 2
        if stem.startswith("Finger"):
            sphere = character_height / 50
        elif stem.startswith(("Neck", "Ankle")):
            sphere = character_height / 10
        elif stem.startswith("Wrist"):
            sphere = character_height / 20
        elif stem.startswith(("Shoulder", "Hip")):
            sphere = character_height / 7
        pieces.append(MannequinPiece(joint, segment.child,
            "Mannequin_Sphere", joint + ("_Sphere1" if foot else "_Sphere"),
            (sphere, sphere, sphere), segment.start, segment.end))
    names = [piece.name for piece in pieces]
    if not names or len(names) != len(set(names)):
        raise ValueError("Mannequin 目标为空或名称重复")
    return tuple(pieces)
