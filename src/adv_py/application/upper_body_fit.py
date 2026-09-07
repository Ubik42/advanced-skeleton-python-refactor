from __future__ import annotations

from adv_py.core.fit_orientation import (
    FitOrientationChildSelection,
    FitOrientationRequest,
)
from adv_py.core.fit_template import (
    synthetic_body_source_fit_template,
    synthetic_upper_body_fit_template,
)

from .oriented_fit_template import (
    BuildOrientedFitTemplate,
    OrientedFitTemplateBuildPlan,
    OrientedFitTemplateBuildResult,
    OrientedFitTemplateHost,
)


UpperBodyFitHost = OrientedFitTemplateHost
UpperBodyFitBuildPlan = OrientedFitTemplateBuildPlan
UpperBodyFitBuildResult = OrientedFitTemplateBuildResult
BodySourceFitBuildPlan = OrientedFitTemplateBuildPlan
BodySourceFitBuildResult = OrientedFitTemplateBuildResult


def upper_body_orientation_request() -> FitOrientationRequest:
    """Return the explicit non-leaf orientation policy for the upper tree."""

    return FitOrientationRequest(
        (
            "Root",
            "Spine1",
            "Spine2",
            "Neck",
            "Head",
            "ClavicleLeft",
            "ShoulderLeft",
            "ElbowLeft",
            "ClavicleRight",
            "ShoulderRight",
            "ElbowRight",
        ),
        (FitOrientationChildSelection("Spine2", "Neck"),),
    )


def body_source_orientation_request() -> FitOrientationRequest:
    """Return explicit choices for torso, ankle, and toe branch joints."""

    return FitOrientationRequest(
        (
            "Root",
            "Spine1",
            "Chest",
            "Neck",
            "Head",
            "Scapula",
            "Shoulder",
            "Elbow",
            "Hip",
            "Knee",
            "Ankle",
            "Toes",
        ),
        (
            FitOrientationChildSelection("Root", "Spine1"),
            FitOrientationChildSelection("Chest", "Neck"),
            FitOrientationChildSelection("Ankle", "Toes"),
            FitOrientationChildSelection("Toes", "ToesEnd"),
        ),
    )


class BuildSyntheticUpperBodyFit:
    """Compatibility entry point for the independent upper body template."""

    def __init__(self, host: UpperBodyFitHost) -> None:
        self._host = host
        self._builder = BuildOrientedFitTemplate(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        scale: float = 1.0,
    ) -> UpperBodyFitBuildPlan:
        return self._builder.plan(
            synthetic_upper_body_fit_template(
                self._host.scene_up_axis(),
                scale=scale,
            ),
            upper_body_orientation_request(),
            container_name,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        scale: float = 1.0,
    ) -> UpperBodyFitBuildResult:
        return self._builder.apply(
            synthetic_upper_body_fit_template(
                self._host.scene_up_axis(),
                scale=scale,
            ),
            upper_body_orientation_request(),
            container_name,
            transaction_label="创建并朝向上半身 FitSkeleton",
            error_context="上半身 FitSkeleton",
        )


class BuildSyntheticBodySourceFit:
    """Build an upper body plus one source leg for later mirror semantics."""

    def __init__(self, host: UpperBodyFitHost) -> None:
        self._host = host
        self._builder = BuildOrientedFitTemplate(host)

    def plan(
        self,
        container_name: str = "FitSkeleton",
        *,
        scale: float = 1.0,
    ) -> BodySourceFitBuildPlan:
        return self._builder.plan(
            synthetic_body_source_fit_template(
                self._host.scene_up_axis(),
                scale=scale,
            ),
            body_source_orientation_request(),
            container_name,
        )

    def apply(
        self,
        container_name: str = "FitSkeleton",
        *,
        scale: float = 1.0,
    ) -> BodySourceFitBuildResult:
        return self._builder.apply(
            synthetic_body_source_fit_template(
                self._host.scene_up_axis(),
                scale=scale,
            ),
            body_source_orientation_request(),
            container_name,
            transaction_label="创建并朝向全身源 FitSkeleton",
            error_context="全身源 FitSkeleton",
        )
