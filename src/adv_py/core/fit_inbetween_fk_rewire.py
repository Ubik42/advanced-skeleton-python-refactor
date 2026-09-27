"""Plan the standard FK chain handoff to an Inbetween FKX chain."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_inbetween_fk_anchor import InbetweenFkAnchorPlan
from .fit_inbetween_fk_parts import InbetweenFkPartsPlan


@dataclass(frozen=True, slots=True)
class InbetweenFkRewirePlan:
    start_fk_control_path: str
    start_fk_driver_path: str
    start_fk_constraint_name: str
    start_fkx_name: str
    downstream_fk_offset_path: str | None
    last_part_fkx_name: str
    follow_constraint_name: str | None


def plan_inbetween_fk_rewire(
    anchor: InbetweenFkAnchorPlan,
    parts: InbetweenFkPartsPlan, *,
    start_fk_driver_path: str,
    start_fk_constraint_name: str,
    downstream_fk_offset_path: str | None,
) -> InbetweenFkRewirePlan:
    if not parts.parts or parts.start_body_name != anchor.start_body_name:
        raise ValueError("Inbetween FK 改接需要完整的 Part 控制链")
    if (not start_fk_driver_path.startswith("|")
            or not start_fk_constraint_name
            or (downstream_fk_offset_path is not None and (
                not downstream_fk_offset_path.startswith("|")
                or downstream_fk_offset_path == anchor.fk_offset_path))):
        raise ValueError("Inbetween FK 改接目标无效")
    return InbetweenFkRewirePlan(
        anchor.fk_control_path,
        start_fk_driver_path, start_fk_constraint_name,
        anchor.fkx_name,
        downstream_fk_offset_path,
        parts.parts[-1].fkx_name,
        ("AdvPy_" + anchor.start_body_name
         + "_InbetweenNextFKFollow"
         if downstream_fk_offset_path is not None else None))
