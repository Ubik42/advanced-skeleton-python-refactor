"""Plan the FKPS/FKMM/PM receiver chain for Inbetween Part controls."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .fit_inbetween_fk_anchor import InbetweenFkAnchorPlan
from .fit_part import FitPartJointSpec


@dataclass(frozen=True, slots=True)
class InbetweenFkPartSpec:
    part_name: str
    index: int
    world_position: tuple[float, float, float]
    rotate_order: int
    parent_fkx_name: str
    fkps_name: str
    offset_name: str
    extra_name: str
    control_name: str
    fkx_name: str
    fk_matrix_name: str
    pick_matrix_name: str
    radius: float

    @property
    def receiver_plug(self) -> str:
        return self.fk_matrix_name + ".matrixIn[0]"


@dataclass(frozen=True, slots=True)
class InbetweenFkPartsPlan:
    start_body_name: str
    fk_system_path: str
    start_fk_control_path: str
    parts: tuple[InbetweenFkPartSpec, ...]

    @property
    def receiver_plugs(self) -> tuple[str, ...]:
        return tuple(part.receiver_plug for part in self.parts)


def plan_inbetween_fk_parts(
    anchor: InbetweenFkAnchorPlan,
    body_parts: tuple[FitPartJointSpec, ...], *,
    fk_system_path: str,
    radius: float,
) -> InbetweenFkPartsPlan:
    """Describe the original OPM Part path with a point source per segment.

    FKPS follows the previous FKX and starts at the Part bind position.
    FKMM combines the Inbetween local rotation, FKPS world matrix and the
    FK system inverse. PM feeds the Part FK Offset without inherited scale.
    """
    if (not fk_system_path.startswith("|")
            or isinstance(radius, bool)
            or not isinstance(radius, (int, float))
            or not isfinite(radius) or radius <= 0 or not body_parts):
        raise ValueError("Inbetween Part FK 需要系统父级和正半径")
    ordered = tuple(sorted(body_parts, key=lambda part: part.index))
    if (any(part.kind != "inbetween"
            or part.start_body_name != anchor.start_body_name
            or part.count != len(ordered)
            or part.index != index
            or part.side != ordered[0].side
            for index, part in enumerate(ordered, 1))
            or len({part.name for part in ordered}) != len(ordered)):
        raise ValueError("Inbetween Part FK 链不连续或混入其他关节")
    result = []
    previous_fkx = anchor.fkx_name
    for part in ordered:
        prefix = "AdvPy_" + part.name + "_Inbetween"
        spec = InbetweenFkPartSpec(
            part.name, part.index, part.world_position,
            part.rotation_order, previous_fkx,
            prefix + "FKPS", prefix + "FKOffset",
            prefix + "FKExtra", prefix + "FK",
            prefix + "FKX", prefix + "FKMM",
            prefix + "PM", float(radius))
        result.append(spec)
        previous_fkx = spec.fkx_name
    return InbetweenFkPartsPlan(
        anchor.start_body_name, fk_system_path,
        anchor.fk_control_path, tuple(result))
