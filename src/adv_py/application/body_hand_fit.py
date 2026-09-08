from __future__ import annotations

from adv_py.core.body_hand_fit import (
    BODY_HAND_DIGITS,
    synthetic_body_with_hand_source_fit_template,
)
from adv_py.core.fit_orientation import (
    FitOrientationChildSelection,
    FitOrientationRequest,
)

from .oriented_fit_template import (
    BuildOrientedFitTemplate,
    OrientedFitTemplateBuildPlan,
    OrientedFitTemplateBuildResult,
    OrientedFitTemplateHost,
)
from .upper_body_fit import body_source_orientation_request


BodyHandSourceFitHost = OrientedFitTemplateHost
BodyHandSourceFitBuildPlan = OrientedFitTemplateBuildPlan
BodyHandSourceFitBuildResult = OrientedFitTemplateBuildResult


def body_with_hand_orientation_request() -> FitOrientationRequest:
    base = body_source_orientation_request()
    finger_joints = tuple(
        f"{digit.value}{segment}"
        for digit in BODY_HAND_DIGITS
        for segment in ("1", "2", "3")
    )
    return FitOrientationRequest(
        base.joints + ("Wrist",) + finger_joints,
        base.child_selections
        + (FitOrientationChildSelection("Wrist", "Middle1"),),
    )


class BuildSyntheticBodyWithHandSourceFit:
    """Build the synthetic body source and one mirrorable five-digit hand."""

    def __init__(self, host: BodyHandSourceFitHost) -> None:
        self._host = host
        self._builder = BuildOrientedFitTemplate(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        scale: float = 1.0,
    ) -> BodyHandSourceFitBuildPlan:
        return self._builder.plan(
            synthetic_body_with_hand_source_fit_template(
                self._host.scene_up_axis(),
                scale=scale,
            ),
            body_with_hand_orientation_request(),
            container_name,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        scale: float = 1.0,
    ) -> BodyHandSourceFitBuildResult:
        return self._builder.apply(
            synthetic_body_with_hand_source_fit_template(
                self._host.scene_up_axis(),
                scale=scale,
            ),
            body_with_hand_orientation_request(),
            container_name,
            transaction_label="创建并朝向五指全身源 FitSkeleton",
            error_context="五指全身源 FitSkeleton",
        )
