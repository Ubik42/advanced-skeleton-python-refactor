"""One transaction for a Body controller's hierarchy, icon, and placement."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_build_options import BodyBuildOptions
from adv_py.core.body_controller_appearance import (
    BodyControllerAppearanceInput, BodyControllerAppearancePlan,
    BodyControllerAppearanceState, audit_body_controller_appearance,
    plan_body_controller_appearance,
)
from adv_py.core.body_controller_layers import (
    BodyControllerLayerSnapshot, BodyControllerLayerSpec,
    audit_body_controller_layers, plan_body_controller_layers,
)
from adv_py.core.fit_settings import FitSkeletonValidationError


class BodyControllerHost(Protocol):
    """The appearance step replaces the main curve made by the layer step."""

    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def capture_controller_appearance_input(
        self, layers: BodyControllerLayerSpec, fit_joint: str,
    ) -> BodyControllerAppearanceInput: ...
    def preflight_controller_appearance(
        self, plan: BodyControllerAppearancePlan,
    ) -> None: ...
    def create_body_controller_layers(
        self, layers: BodyControllerLayerSpec,
    ) -> None: ...
    def apply_controller_appearance(
        self, plan: BodyControllerAppearancePlan,
    ) -> None: ...
    def capture_body_controller_layers(
        self, layers: BodyControllerLayerSpec,
    ) -> BodyControllerLayerSnapshot: ...
    def capture_controller_appearance(
        self, plan: BodyControllerAppearancePlan,
    ) -> BodyControllerAppearanceState: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class BodyControllerBuildPlan:
    layers: BodyControllerLayerSpec
    appearance: BodyControllerAppearancePlan


@dataclass(frozen=True, slots=True)
class BodyControllerBuildResult:
    plan: BodyControllerBuildPlan
    layers: BodyControllerLayerSnapshot
    appearance: BodyControllerAppearanceState


class BuildBodyController:
    def __init__(self, host: BodyControllerHost) -> None:
        self._host = host

    def plan(
        self, kind: str, name: str, side: str, parent_path: str,
        fit_joint: str, options: BodyBuildOptions,
    ) -> BodyControllerBuildPlan:
        layers = plan_body_controller_layers(
            kind, name, side, parent_path, options)
        collisions = tuple(sorted({path
            for node_name in (path.rsplit("|", 1)[-1]
                              for path in layers.transform_paths)
            for path in self._host.find_name_collisions(node_name)}))
        if collisions:
            raise FitSkeletonValidationError(
                "Body 控制器名称冲突：" + "、".join(collisions))
        source = self._host.capture_controller_appearance_input(
            layers, fit_joint)
        if source.layers != layers or source.fit_joint != fit_joint:
            raise ValueError("控制器外观捕获与层级计划不一致")
        appearance = plan_body_controller_appearance(source)
        self._host.preflight_controller_appearance(appearance)
        return BodyControllerBuildPlan(layers, appearance)

    def apply(
        self, kind: str, name: str, side: str, parent_path: str,
        fit_joint: str, options: BodyBuildOptions,
    ) -> BodyControllerBuildResult:
        plan = self.plan(kind, name, side, parent_path, fit_joint, options)
        with self._host.transaction("创建 Body 控制器"):
            self._host.create_body_controller_layers(plan.layers)
            self._host.apply_controller_appearance(plan.appearance)
            layers = self._host.capture_body_controller_layers(plan.layers)
            appearance = self._host.capture_controller_appearance(
                plan.appearance)
            issues = audit_body_controller_layers(plan.layers, layers)
            issues += audit_body_controller_appearance(
                plan.appearance, appearance)
            if issues:
                raise RuntimeError("Body 控制器写后状态不符："
                                   + "；".join(issues))
        return BodyControllerBuildResult(plan, layers, appearance)
