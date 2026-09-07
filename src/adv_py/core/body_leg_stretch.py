from __future__ import annotations

from typing import Mapping

from .body_leg_ik import BodyLegIkPlan
from .body_leg_mechanisms import BodyLegMechanismPlan
from .body_limb_stretch import (
    BodyLimbStretchIssue,
    BodyLimbStretchPlan,
    BodyLimbStretchSideSpec,
    BodyLimbStretchSideState,
    BodyLimbStretchSnapshot,
    BodyLimbStretchValidationError,
    audit_body_limb_stretch,
    compensated_stretch_ratio,
    plan_body_limb_stretch,
)
from .fit_symmetry import FitBuildSide


BodyLegStretchIssue = BodyLimbStretchIssue
BodyLegStretchPlan = BodyLimbStretchPlan
BodyLegStretchSideSpec = BodyLimbStretchSideSpec
BodyLegStretchSideState = BodyLimbStretchSideState
BodyLegStretchSnapshot = BodyLimbStretchSnapshot
BodyLegStretchValidationError = BodyLimbStretchValidationError


def plan_body_leg_stretch(
    mechanisms: BodyLegMechanismPlan,
    ik: BodyLegIkPlan,
    *,
    alignment_tolerance: float = 1e-4,
) -> BodyLegStretchPlan:
    targets = {spec.side: spec.ankle_control_path for spec in ik.limbs}
    return plan_body_limb_stretch(
        mechanisms,
        targets,
        limb_label="Leg",
        alignment_tolerance=alignment_tolerance,
    )


def audit_body_leg_stretch(
    plan: BodyLegStretchPlan,
    snapshot: BodyLegStretchSnapshot,
    *,
    tolerance: float = 1e-4,
    expected_segment_factor_sources_by_side: Mapping[
        FitBuildSide,
        tuple[str, str],
    ] | None = None,
) -> tuple[BodyLegStretchIssue, ...]:
    return audit_body_limb_stretch(
        plan,
        snapshot,
        tolerance=tolerance,
        expected_segment_factor_sources_by_side=(
            expected_segment_factor_sources_by_side
        ),
    )
