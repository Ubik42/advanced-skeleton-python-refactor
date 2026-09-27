"""A single FK source for Inbetween segments without an IK mechanism."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_inbetween_fk_parts import InbetweenFkPartsPlan


@dataclass(frozen=True, slots=True)
class InbetweenFkBodyDriverSpec:
    body_part_name: str
    fkx_name: str
    constraint_name: str


@dataclass(frozen=True, slots=True)
class InbetweenFkBodyDriverPlan:
    parts: tuple[InbetweenFkBodyDriverSpec, ...]


def plan_inbetween_fk_body_drivers(
    fk: InbetweenFkPartsPlan,
) -> InbetweenFkBodyDriverPlan:
    if not fk.parts:
        raise ValueError("Inbetween FK Body 驱动缺少 Part 控制链")
    return InbetweenFkBodyDriverPlan(tuple(
        InbetweenFkBodyDriverSpec(
            part.part_name, part.fkx_name,
            "AdvPy_" + part.part_name + "_InbetweenFKOrient",
        ) for part in fk.parts
    ))
