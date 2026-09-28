"""Local FK scale links for controls that drive Body joints directly."""
from __future__ import annotations

from dataclasses import dataclass

from .body_limb_controls import BodyLimbFkControlSpec
from .body_skeleton import BodySkeletonSnapshot


@dataclass(frozen=True, slots=True)
class BodyDirectFkScaleSpec:
    body_joint: str
    source_scale: str


def plan_body_direct_fk_scales(
    body: BodySkeletonSnapshot,
    controls: tuple[BodyLimbFkControlSpec, ...],
) -> tuple[BodyDirectFkScaleSpec, ...]:
    """Exclude Root, whose local scale is already owned by Character Global."""
    body_paths = {joint.path for joint in body.joints}
    result = tuple(BodyDirectFkScaleSpec(
        control.driven_joint, control.control_path + ".scale")
        for control in controls
        if control.driven_joint in body_paths
        and control.driven_joint != body.root)
    if len({spec.body_joint for spec in result}) != len(result):
        raise ValueError("Body FK 缩放目标重复")
    return result
