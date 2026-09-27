"""Distribute downstream FK axial twist over an Inbetween Part chain."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_part import FitPartJointSpec


@dataclass(frozen=True, slots=True)
class InbetweenUnTwisterStep:
    part_name: str
    constraint_name: str
    index: int
    count: int
    amount_name: str

    @property
    def fraction(self) -> float:
        return self.index / (self.count + 1)


@dataclass(frozen=True, slots=True)
class InbetweenUnTwisterPlan:
    end_fk_control_path: str
    end_fk_offset_path: str
    relative_matrix_name: str
    decompose_name: str
    quaternion_name: str
    steps: tuple[InbetweenUnTwisterStep, ...]

    @property
    def twist_plug(self) -> str:
        return self.quaternion_name + ".outputRotateX"


def plan_inbetween_untwister(
    parts: tuple[FitPartJointSpec, ...],
    constraint_names: tuple[str, ...], *,
    end_fk_control_path: str,
    end_fk_offset_path: str,
) -> InbetweenUnTwisterPlan:
    """Use the end FK controller's local twist as the distributed source.

    The MEL OPM branch inserts each weighted X rotation into the Part
    matrix. This rig uses an orientConstraint for the final FK/IK rotation;
    its offsetX is the equivalent insertion point used by the MEL fallback.
    """
    if (not parts or len(parts) != len(constraint_names)
            or not end_fk_offset_path.startswith("|")
            or not end_fk_control_path.startswith(
                end_fk_offset_path + "|")):
        raise ValueError("Inbetween UnTwister 需要完整的末端 FK 控制层")
    ordered = tuple(sorted(zip(parts, constraint_names),
                           key=lambda pair: pair[0].index))
    first = ordered[0][0]
    if (len({part.name for part, _ in ordered}) != len(ordered)
            or len(set(constraint_names)) != len(constraint_names)
            or any(part.kind != "inbetween"
                   or part.start_body != first.start_body
                   or part.end_body != first.end_body
                   or part.count != len(ordered)
                   or part.index != index
                   or not constraint
                   for index, (part, constraint) in enumerate(ordered, 1))):
        raise ValueError("Inbetween UnTwister Part 链不连续")
    prefix = "AdvPy_" + first.start_body_name + "_InbetweenUnTwister"
    return InbetweenUnTwisterPlan(
        end_fk_control_path, end_fk_offset_path,
        prefix + "Relative", prefix + "Decompose", prefix + "Quaternion",
        tuple(InbetweenUnTwisterStep(
            part.name, constraint, part.index, part.count,
            "AdvPy_" + part.name + "_UnTwisterAmount",
        ) for part, constraint in ordered),
    )
