"""Wheel and rolling-ball FK inputs from AdvancedSkeleton 6.925."""
from __future__ import annotations

from dataclasses import dataclass

from .body_limb_controls import BodyLimbFkControlSpec
from .fit_metadata import FitJointMetadata
from .fit_symmetry import FitSymmetryInstance


@dataclass(frozen=True, slots=True)
class BodyFitWheelSpec:
    fit_joint: str
    control: BodyLimbFkControlSpec
    rolling_ball: bool
    source_position: tuple[float, float, float]
    side_factor: int
    scale_plug: str


def plan_body_fit_wheels(
    metadata: tuple[FitJointMetadata, ...],
    instances: tuple[FitSymmetryInstance, ...],
    controls: tuple[BodyLimbFkControlSpec, ...],
    *, scale_plug: str,
) -> tuple[BodyFitWheelSpec, ...]:
    """Match source Fit markers to each built side's real FK control."""
    marked = {item.joint: item for item in metadata
              if item.wheel or item.rolling_ball}
    if not marked:
        return ()
    by_name = {
        (name, control.side.value): control
        for control in controls for name in control.fit_joint_names
    }
    result: list[BodyFitWheelSpec] = []
    for instance in instances:
        item = marked.get(instance.source_joint)
        if item is None:
            continue
        name = instance.output_name.rsplit("_", 1)[0]
        control = by_name.get((name, instance.side.value))
        # The MEL builder also skips a marker when no FK controller exists.
        if control is None:
            continue
        result.append(BodyFitWheelSpec(
            fit_joint=instance.source_joint,
            control=control,
            rolling_ball=item.rolling_ball,
            source_position=instance.world_position,
            side_factor=-1 if instance.side.value == "L" else 1,
            scale_plug=scale_plug,
        ))
    return tuple(result)
