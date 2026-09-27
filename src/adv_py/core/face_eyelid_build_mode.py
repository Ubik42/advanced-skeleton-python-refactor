"""Select the eyelid chains built by the regular or simpler 6.925 option."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FaceEyeLidBuildMode:
    simpler_eyelid: bool
    include_outer_segments: bool
    expected_arc_controls: int
    minimum_segment_joints: int


def plan_face_eye_lid_build_mode(simpler_eyelid: bool) -> FaceEyeLidBuildMode:
    if type(simpler_eyelid) is not bool:
        raise ValueError("简化眼睑模式必须是布尔值")
    return FaceEyeLidBuildMode(
        simpler_eyelid=simpler_eyelid,
        include_outer_segments=not simpler_eyelid,
        expected_arc_controls=4 if simpler_eyelid else 8,
        minimum_segment_joints=8 if simpler_eyelid else 16,
    )
