"""Create one source-shaped controller hierarchy through an explicit host port."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_build_options import BodyBuildOptions
from adv_py.core.body_controller_layers import (
    BodyControllerLayerSnapshot, BodyControllerLayerSpec,
    audit_body_controller_layers, plan_body_controller_layers,
)
from adv_py.core.fit_settings import FitSkeletonValidationError


class BodyControllerLayersHost(Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...

    def capture_body_controller_layers(
        self, spec: BodyControllerLayerSpec,
    ) -> BodyControllerLayerSnapshot: ...

    def create_body_controller_layers(
        self, spec: BodyControllerLayerSpec,
    ) -> None: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True, slots=True)
class BodyControllerLayersBuildPlan:
    layers: BodyControllerLayerSpec
    name_collisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.name_collisions


@dataclass(frozen=True, slots=True)
class BodyControllerLayersBuildResult:
    plan: BodyControllerLayersBuildPlan
    snapshot: BodyControllerLayerSnapshot


class BuildBodyControllerLayers:
    """One controller's topology and optional Sub/Extra curves.

    Joint alignment, icon selection, and constraint wiring belong to the
    higher-level rig build, which uses the returned control path.
    """

    def __init__(self, host: BodyControllerLayersHost) -> None:
        self._host = host

    def plan(
        self, kind: str, name: str, side: str, parent_path: str,
        options: BodyBuildOptions,
    ) -> BodyControllerLayersBuildPlan:
        layers = plan_body_controller_layers(
            kind, name, side, parent_path, options)
        names = tuple(path.rsplit("|", 1)[-1]
                      for path in layers.transform_paths)
        collisions = tuple(sorted({path for node_name in names
                                   for path in self._host.find_name_collisions(
                                       node_name)}))
        return BodyControllerLayersBuildPlan(layers, collisions)

    def apply(
        self, kind: str, name: str, side: str, parent_path: str,
        options: BodyBuildOptions,
    ) -> BodyControllerLayersBuildResult:
        plan = self.plan(kind, name, side, parent_path, options)
        if not plan.ready:
            raise FitSkeletonValidationError(
                "控制器名称冲突：" + "、".join(plan.name_collisions))
        with self._host.transaction("创建 " + plan.layers.control_path):
            self._host.create_body_controller_layers(plan.layers)
            snapshot = self._host.capture_body_controller_layers(plan.layers)
            issues = audit_body_controller_layers(plan.layers, snapshot)
            if issues:
                raise RuntimeError("控制器创建复检失败：" + "；".join(issues))
        return BodyControllerLayersBuildResult(plan, snapshot)
