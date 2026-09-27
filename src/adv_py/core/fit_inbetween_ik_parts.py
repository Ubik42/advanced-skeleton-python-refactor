"""Plan Inbetween IKX segment sources from the existing limb IK chain."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .fit_part import FitPartJointSpec


@dataclass(frozen=True, slots=True)
class InbetweenIkPartSpec:
    body_part_name: str
    index: int
    count: int
    parent_ikx_name: str
    ikx_name: str
    distance_name: str
    rotate_order: int
    world_position: tuple[float, float, float]

    @property
    def interval_fraction(self) -> float:
        return 1.0 / (self.count + 1)


@dataclass(frozen=True, slots=True)
class InbetweenIkPartsPlan:
    start_ik_driver: str
    end_ik_driver: str
    parts: tuple[InbetweenIkPartSpec, ...]


def plan_inbetween_ik_parts(
    body_parts: tuple[FitPartJointSpec, ...], *,
    start_ik_driver: str,
    end_ik_driver: str,
) -> InbetweenIkPartsPlan:
    """Insert IKX markers at equal intervals of a solved IK segment.

    The standard Python rig already solves its start/end IK driver joints.
    Each new IKX follows the start driver and receives one equal share of
    the end driver's local translation on all three axes. This preserves
    animated segment length without rebuilding the existing IK handle.
    """
    if (not start_ik_driver or not end_ik_driver
            or start_ik_driver == end_ik_driver or not body_parts):
        raise ValueError("Inbetween IK 需要明确的起止机制关节")
    ordered = tuple(sorted(body_parts, key=lambda item: item.index))
    if (len({part.name for part in ordered}) != len(ordered)
            or any(part.kind != "inbetween"
                   or part.start_body != ordered[0].start_body
                   or part.end_body != ordered[0].end_body
                   or part.index != index
                   or part.count != len(ordered)
                   or len(part.world_position) != 3
                   or not all(isfinite(value) for value in part.world_position)
                   for index, part in enumerate(ordered, 1))):
        raise ValueError("Inbetween IK Part 链不连续")
    result = []
    parent = start_ik_driver
    for part in ordered:
        prefix = "AdvPy_" + part.name + "_Inbetween"
        spec = InbetweenIkPartSpec(
            part.name, part.index, part.count, parent,
            prefix + "IKX", prefix + "IKDistance",
            part.rotation_order, part.world_position)
        result.append(spec)
        parent = spec.ikx_name
    return InbetweenIkPartsPlan(
        start_ik_driver, end_ik_driver, tuple(result))
