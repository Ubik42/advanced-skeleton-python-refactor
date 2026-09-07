from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_container import (
    LOCKED_FIT_CHANNELS,
    FitContainerState,
    FitUpAxis,
)
from adv_py.core.fit_orientation import (
    IDENTITY_AXES,
    FitJointOrientationState,
    FitOrientationChange,
    FitOrientationRequest,
    FitOrientationSnapshot,
    plan_simple_fit_orientations,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_template import (
    FitTemplateSpec,
    predict_fit_template_hierarchy,
)

from .fit_orientation import (
    FitOrientationHost,
    FitOrientationResult,
    OrientSimpleFitChain,
)
from .fit_template import (
    CreateFitTemplate,
    FitTemplateCreatePlan,
    FitTemplateCreateResult,
    FitTemplateHost,
)


class OrientedFitTemplateHost(FitTemplateHost, FitOrientationHost, Protocol):
    def inspect_fit_container(self, name: str) -> FitContainerState: ...


@dataclass(frozen=True, slots=True)
class OrientedFitTemplateBuildPlan:
    template_plan: FitTemplateCreatePlan
    orientation_request: FitOrientationRequest
    predicted_orientation_changes: tuple[FitOrientationChange, ...]
    container_errors: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.template_plan.ready and not self.container_errors

    @property
    def blockers(self) -> tuple[str, ...]:
        return self.template_plan.blockers + self.container_errors


@dataclass(frozen=True, slots=True)
class OrientedFitTemplateBuildResult:
    plan: OrientedFitTemplateBuildPlan
    template: FitTemplateCreateResult
    orientation: FitOrientationResult


class BuildOrientedFitTemplate:
    """Create and orient a validated template in one host transaction."""

    def __init__(self, host: OrientedFitTemplateHost) -> None:
        self._host = host
        self._template_creator = CreateFitTemplate(host)
        self._orientation_editor = OrientSimpleFitChain(host)

    def plan(
        self,
        template: FitTemplateSpec,
        request: FitOrientationRequest,
        container_name: str = "FitSkeleton",
    ) -> OrientedFitTemplateBuildPlan:
        up_axis = self._host.scene_up_axis()
        template_plan = self._template_creator.plan(template, container_name)
        state = self._host.inspect_fit_container(
            template_plan.before_hierarchy.container
        )
        container_errors = self._container_errors(state)
        predicted_changes: tuple[FitOrientationChange, ...] = ()
        if template_plan.ready and not container_errors:
            predicted_changes = self._predict_orientation_changes(
                template,
                template_plan.before_hierarchy.container,
                up_axis,
                request,
            )
        return OrientedFitTemplateBuildPlan(
            template_plan,
            request,
            predicted_changes,
            container_errors,
        )

    def apply(
        self,
        template: FitTemplateSpec,
        request: FitOrientationRequest,
        container_name: str = "FitSkeleton",
        *,
        transaction_label: str = "创建并朝向 FitSkeleton 模板",
        error_context: str = "FitSkeleton 模板",
    ) -> OrientedFitTemplateBuildResult:
        plan = self.plan(template, request, container_name)
        if not plan.ready:
            raise FitSkeletonValidationError(
                f"{error_context}预检失败，场景未修改："
                + "；".join(plan.blockers)
            )

        with self._host.transaction(transaction_label):
            template_result = self._template_creator.apply_plan_in_transaction(
                plan.template_plan
            )
            actual_orientation_plan = self._orientation_editor.plan(
                plan.orientation_request,
                template_result.hierarchy.container,
            )
            if actual_orientation_plan.changes != plan.predicted_orientation_changes:
                raise RuntimeError(
                    f"{error_context}创建后计划漂移，已回滚整个事务"
                )
            orientation_result = self._orientation_editor.apply_plan_in_transaction(
                actual_orientation_plan
            )
        return OrientedFitTemplateBuildResult(
            plan,
            template_result,
            orientation_result,
        )

    @staticmethod
    def _container_errors(state: FitContainerState) -> tuple[str, ...]:
        errors: list[str] = []
        if state.path != f"|{state.short_name}":
            errors.append("FitSkeleton 容器必须位于场景根级")
        missing_locks = LOCKED_FIT_CHANNELS - state.locked_channels
        if missing_locks:
            errors.append("FitSkeleton 容器缺少平移/旋转锁定")
        if any(abs(value) > 1e-5 for value in state.local_translation):
            errors.append("FitSkeleton 容器平移必须为零")
        if any(abs(value) > 1e-5 for value in state.local_rotation):
            errors.append("FitSkeleton 容器旋转必须为零")
        if any(abs(value - 1.0) > 1e-5 for value in state.local_scale):
            errors.append("FitSkeleton 容器缩放必须为一")
        return tuple(errors)

    @staticmethod
    def _predict_orientation_changes(
        template: FitTemplateSpec,
        container_path: str,
        up_axis: FitUpAxis,
        request: FitOrientationRequest,
    ) -> tuple[FitOrientationChange, ...]:
        hierarchy = predict_fit_template_hierarchy(template, container_path)
        snapshot = FitOrientationSnapshot(
            hierarchy=hierarchy,
            up_axis=up_axis,
            joints=tuple(
                FitJointOrientationState(
                    joint=node.path,
                    joint_orient=(0.0, 0.0, 0.0),
                    rotation=(0.0, 0.0, 0.0),
                    world_axes=IDENTITY_AXES,
                )
                for node in hierarchy.joints
            ),
        )
        return plan_simple_fit_orientations(snapshot, request)
