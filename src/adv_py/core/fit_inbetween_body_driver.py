"""Plan FK/IK orientation sources for final Inbetween Body Parts."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_inbetween_fk_parts import InbetweenFkPartsPlan
from .fit_inbetween_ik_parts import InbetweenIkPartsPlan


@dataclass(frozen=True, slots=True)
class InbetweenBodyDriverSpec:
    body_part_name: str
    fkx_name: str
    ikx_name: str
    constraint_name: str


@dataclass(frozen=True, slots=True)
class InbetweenBodyDriverPlan:
    fk_weight_plug: str
    ik_weight_plug: str
    parts: tuple[InbetweenBodyDriverSpec, ...]


def plan_inbetween_body_drivers(
    fk: InbetweenFkPartsPlan,
    ik: InbetweenIkPartsPlan, *,
    fk_weight_plug: str,
    ik_weight_plug: str,
) -> InbetweenBodyDriverPlan:
    """Reuse the character's limb mode weights for every Part orientation.

    The Body Part hierarchy already distributes its translation over the
    segment. Only rotation is blended here; connecting another point driver
    would compete with that length graph.
    """
    if (not fk_weight_plug or not ik_weight_plug
            or fk_weight_plug == ik_weight_plug
            or len(fk.parts) != len(ik.parts)
            or not fk.parts):
        raise ValueError("Inbetween Body FK／IK 输入不完整")
    result = []
    for fk_part, ik_part in zip(fk.parts, ik.parts):
        if (fk_part.part_name != ik_part.body_part_name
                or fk_part.index != ik_part.index):
            raise ValueError("Inbetween Body FK／IK Part 顺序不一致")
        result.append(InbetweenBodyDriverSpec(
            fk_part.part_name, fk_part.fkx_name,
            ik_part.ikx_name,
            "AdvPy_" + fk_part.part_name + "_InbetweenIKFKOrient"))
    return InbetweenBodyDriverPlan(
        fk_weight_plug, ik_weight_plug, tuple(result))
