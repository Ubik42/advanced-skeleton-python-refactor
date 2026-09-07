from __future__ import annotations

from typing import Mapping

from .body_leg_blend import BodyLegBlendPlan
from .body_leg_stretch import BodyLegStretchPlan
from .body_leg_twist import BodyLegTwistPlan
from .body_limb_volume import (
    BodyLimbVolumeIssue,
    BodyLimbVolumePlan,
    BodyLimbVolumeSideSpec,
    BodyLimbVolumeSideState,
    BodyLimbVolumeSnapshot,
    BodyLimbVolumeValidationError,
    audit_body_limb_volume,
    plan_body_limb_volume,
    volume_preservation_scale,
)
from .fit_symmetry import FitBuildSide


BodyLegVolumeIssue = BodyLimbVolumeIssue
BodyLegVolumePlan = BodyLimbVolumePlan
BodyLegVolumeSideSpec = BodyLimbVolumeSideSpec
BodyLegVolumeSideState = BodyLimbVolumeSideState
BodyLegVolumeSnapshot = BodyLimbVolumeSnapshot
BodyLegVolumeValidationError = BodyLimbVolumeValidationError


def plan_body_leg_volume(
    stretch: BodyLegStretchPlan,
    twist: BodyLegTwistPlan,
    blend: BodyLegBlendPlan,
    *,
    stretch_ratio_sources_by_side: Mapping[FitBuildSide, str] | None = None,
) -> BodyLegVolumePlan:
    return plan_body_limb_volume(
        stretch,
        twist,
        blend,
        limb_label="Leg",
        stretch_ratio_sources_by_side=stretch_ratio_sources_by_side,
    )


def audit_body_leg_volume(
    plan: BodyLegVolumePlan,
    snapshot: BodyLegVolumeSnapshot,
    *,
    tolerance: float = 1e-4,
) -> tuple[BodyLegVolumeIssue, ...]:
    return audit_body_limb_volume(plan, snapshot, tolerance=tolerance)
