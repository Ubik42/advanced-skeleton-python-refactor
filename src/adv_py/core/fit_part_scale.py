"""Plan non-OPM Part scaling from Fit chains and rig control channels."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_part import FitPartJointSpec


@dataclass(frozen=True, slots=True)
class FitPartScaleStep:
    part_name: str
    start_body_name: str
    source_plug: str
    target_plug: str


@dataclass(frozen=True, slots=True)
class FitPartLimbScaleChain:
    start_body_name: str
    part_names: tuple[str, ...]
    fk_scale_plug: str
    volume_plug: str
    mode_plug: str
    fatness_control: str
    fatness_attribute: str
    blend_name: str
    fatness_add_name: str

    @property
    def output_plug(self) -> str:
        return self.blend_name + ".output"


@dataclass(frozen=True, slots=True)
class FitPartScalePlan:
    direct: tuple[FitPartScaleStep, ...]
    limbs: tuple[FitPartLimbScaleChain, ...]


def plan_fit_part_scale(
    parts: tuple[FitPartJointSpec, ...],
) -> FitPartScalePlan:
    """Use explicit FK/IK volume for limbs and Body scale for other chains.

    With segment scale compensation enabled, each Part cancels its parent's
    scale and reapplies the segment scale. OPM chains inherit the matrix scale
    through their parent, so wiring it to every Part would compound it.
    """
    if len({part.name for part in parts}) != len(parts):
        raise ValueError("Fit Part 缩放计划存在重名关节")
    grouped: dict[str, list[FitPartJointSpec]] = {}
    for part in parts:
        if part.segment_scale_compensate:
            grouped.setdefault(part.start_body_name, []).append(part)
    direct = []
    limbs = []
    for start, chain in grouped.items():
        chain.sort(key=lambda part: part.index)
        stem, side = start.rsplit("_", 1)
        if stem in ("Shoulder", "Elbow", "Hip"):
            module = "Arm" if stem != "Hip" else "Leg"
            prefix = f"AdvPy_{stem}_FitPart_{side}"
            limbs.append(FitPartLimbScaleChain(
                start, tuple(part.name for part in chain),
                f"AdvPy_{stem}FK_{side}.scale",
                f"AdvPy_{module}VolumeBlend_{side}.outputR",
                f"AdvPy_{module}Settings.{module.lower()}IkFk_{side}",
                f"AdvPy_{module}IK_{side}",
                "Fatness2" if stem == "Elbow" else "Fatness1",
                prefix + "ScaleBlend", prefix + "FatnessAdd",
            ))
        else:
            direct.extend(FitPartScaleStep(
                part.name, start, start + ".scale", part.name + ".scale",
            ) for part in chain)
    return FitPartScalePlan(tuple(direct), tuple(limbs))
