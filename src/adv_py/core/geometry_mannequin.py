"""Plan the 6.925 Mannequin template pieces for Body segments."""
from __future__ import annotations

from dataclasses import dataclass
from math import dist, isfinite
from fnmatch import fnmatchcase


Vec3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class MannequinSegment:
    joint: str
    child: str
    start: Vec3
    end: Vec3
    heel: Vec3 | None = None


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
                or not segment.child or not isfinite(length)):
            raise ValueError("Mannequin 骨段无效：" + joint)
        if fnmatchcase(joint,'*Part[0-9]*'):
            continue
        stem = joint[:-2]
        axial = (joint == "Root_M" or any(fnmatchcase(joint,pattern) for pattern in
                 ('*Spine[0-9]*','*Chest*','*Head_*')))
        if axial:
            source = "Mannequin_Head" if fnmatchcase(joint,'Head_*') else "Mannequin_Root"
            pieces.append(MannequinPiece(joint, segment.child, source,
                joint + "_Root", (length, character_height / 10,
                                  character_height / 10),
                segment.start, segment.end))
        if any(fnmatchcase(joint,pattern) for pattern in
               ('Spine[0-9]*','Root_M','Chest_M','Jaw_M','Head_*','Eye_*')):
            continue
        foot = 'Ankle' in joint or joint.startswith('Toes')
        if foot:
            source, suffix = "Mannequin_Foot", "_Sphere"
            foot_start = (segment.heel if 'Ankle' in joint
                          and segment.heel is not None else segment.start)
            foot_length = dist(foot_start, segment.end)
            if 'Ankle' in joint and segment.heel is not None:
                foot_length *= 0.87
            scale = (foot_length, foot_length, foot_length)
        else:
            source, suffix = "Mannequin_Limb", "_Limb"
            scale = (length, length / 2, length / 2)
            if stem.startswith("Wrist"):
                scale = (scale[0], scale[1] * 3, scale[2])
            if 'Finger' in joint:
                scale = (length, character_height / 70,
                         character_height / 70)
            if 'Neck' in joint:
                scale = (length * 1.1, character_height / 10,
                         character_height / 10)
            if joint.endswith('_L'):scale=(-scale[0],scale[1],scale[2])
        pieces.append(MannequinPiece(joint, segment.child, source,
            joint + suffix, scale,
            foot_start if foot else segment.start, segment.end))
        sphere = length / 2
        if 'Finger' in joint:
            sphere = character_height / 50
        elif 'Neck' in joint or 'Ankle' in joint:
            sphere = character_height / 10
        elif stem.startswith("Wrist"):
            sphere = character_height / 20
        elif fnmatchcase(joint,'Shoulder_*') or fnmatchcase(joint,'Hip_*'):
            sphere = character_height / 7
        pieces.append(MannequinPiece(joint, segment.child,
            "Mannequin_Sphere", joint + ("_Sphere1" if foot else "_Sphere"),
            (sphere, sphere, sphere), segment.start, segment.end))
    names = [piece.name for piece in pieces]
    if not names or len(names) != len(set(names)):
        raise ValueError("Mannequin 目标为空或名称重复")
    return tuple(pieces)
