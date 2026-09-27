"""Plan scale inheritance for the original non-OPM Fit Part branch."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_part import FitPartJointSpec


@dataclass(frozen=True, slots=True)
class FitPartScaleStep:
    part_name: str
    start_body_name: str
    source_plug: str
    target_plug: str


def plan_fit_part_scale(
    parts: tuple[FitPartJointSpec, ...],
) -> tuple[FitPartScaleStep, ...]:
    """Use the Body segment's resolved FK/IK/volume scale for every Part.

    With segment scale compensation enabled, each Part cancels its parent's
    scale and reapplies the segment scale. OPM chains inherit the matrix scale
    through their parent, so wiring it to every Part would compound it.
    """
    if len({part.name for part in parts}) != len(parts):
        raise ValueError("Fit Part 缩放计划存在重名关节")
    return tuple(FitPartScaleStep(
        part.name, part.start_body_name,
        part.start_body_name + ".scale", part.name + ".scale",
    ) for part in parts if part.segment_scale_compensate)
