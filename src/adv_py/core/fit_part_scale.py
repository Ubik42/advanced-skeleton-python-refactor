"""Plan Fit Part and starting Body scale from rig control channels."""
from __future__ import annotations

from dataclasses import dataclass

from .body_skeleton import BodyJointSpec
from .fit_part import FitPartJointSpec


@dataclass(frozen=True, slots=True)
class FitPartScaleStep:
    part_name: str
    start_body_name: str
    source_plug: str
    target_plug: str


@dataclass(frozen=True, slots=True)
class FitPartInheritedScaleChain:
    start_body_name: str
    part_names: tuple[str, ...]


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
    use_offset_parent_matrix: bool = False
    scale_compose_name: str | None = None
    scale_matrix_name: str | None = None

    @property
    def output_plug(self) -> str:
        return self.blend_name + ".output"


@dataclass(frozen=True, slots=True)
class FitPartScalePlan:
    direct: tuple[FitPartScaleStep, ...]
    limbs: tuple[FitPartLimbScaleChain, ...]
    inherited: tuple[FitPartInheritedScaleChain, ...] = ()


def plan_fit_part_scale(
    parts: tuple[FitPartJointSpec, ...],
    body_joints: tuple[BodyJointSpec, ...] = (),
) -> FitPartScalePlan:
    """Use FK/IK scale on limb Body even when a segment has no Parts.

    With segment scale compensation enabled, each Part cancels its parent's
    scale and reapplies the segment scale. OPM chains inherit the matrix scale
    through their parent, so wiring it to every Part would compound it.
    """
    if len({part.name for part in parts}) != len(parts):
        raise ValueError("Fit Part 缩放计划存在重名关节")
    grouped: dict[str, list[FitPartJointSpec]] = {}
    for part in parts:
        grouped.setdefault(part.start_body_name, []).append(part)
    limb_stems = frozenset(("Shoulder", "Elbow", "Hip", "Knee"))
    body_by_name = {joint.name: joint for joint in body_joints}
    if len(body_by_name) != len(body_joints):
        raise ValueError("Fit Part 缩放计划存在重名 Body 关节")
    for name in body_by_name:
        stem, _, side = name.rpartition("_")
        if stem in limb_stems and side in ("R", "L"):
            grouped.setdefault(name, [])
    direct = []
    limbs = []
    inherited = []
    for start, chain in grouped.items():
        chain.sort(key=lambda part: part.index)
        stem, side = start.rsplit("_", 1)
        body = body_by_name.get(start)
        if body is not None and chain and any(
                part.segment_scale_compensate
                != body.segment_scale_compensate for part in chain):
            raise ValueError("Fit Part 与 Body 缩放补偿模式不一致：" + start)
        use_opm = not (chain[0].segment_scale_compensate if chain
                       else body.segment_scale_compensate)
        if any(part.segment_scale_compensate
               != chain[0].segment_scale_compensate for part in chain):
            raise ValueError("Fit Part 链的缩放补偿模式不一致：" + start)
        if stem in limb_stems:
            module = "Arm" if stem in ("Shoulder", "Elbow") else "Leg"
            prefix = f"AdvPy_{stem}_FitPart_{side}"
            limbs.append(FitPartLimbScaleChain(
                start, tuple(part.name for part in chain),
                f"AdvPy_{stem}FK_{side}.scale",
                f"AdvPy_{module}VolumeBlend_{side}.outputR",
                f"AdvPy_{module}Settings.{module.lower()}IkFk_{side}",
                f"AdvPy_{module}IK_{side}",
                "Fatness2" if stem in ("Elbow", "Knee") else "Fatness1",
                prefix + "ScaleBlend", prefix + "FatnessAdd",
                use_opm,
                prefix + "ScaleCompose" if use_opm else None,
                prefix + "ScaleMatrix" if use_opm else None,
            ))
        elif not use_opm:
            direct.extend(FitPartScaleStep(
                part.name, start, start + ".scale", part.name + ".scale",
            ) for part in chain)
        else:
            inherited.append(FitPartInheritedScaleChain(
                start, tuple(part.name for part in chain)))
    return FitPartScalePlan(tuple(direct), tuple(limbs), tuple(inherited))
