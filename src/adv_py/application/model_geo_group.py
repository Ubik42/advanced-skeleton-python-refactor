"""Create the original Model Cleaner geo root and group model assemblies."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.model_geo_group import (
    ModelAssembly, ModelGeoGroupPlan, plan_model_geo_group,
)


class ModelGeoGroupHost(Protocol):
    def capture_model_assemblies(self) -> tuple[ModelAssembly, ...]: ...
    def apply_model_geo_group(self, plan: ModelGeoGroupPlan) -> tuple[str, ...]: ...


class CreateModelGeoGroup:
    def __init__(self, host: ModelGeoGroupHost) -> None:
        self._host = host

    def execute(self) -> tuple[str, ...]:
        plan = plan_model_geo_group(self._host.capture_model_assemblies())
        return self._host.apply_model_geo_group(plan)
