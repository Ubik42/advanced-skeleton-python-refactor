"""Stage, verify, then replace a Model Clean scene through a host port."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.model_clean import (
    ModelCleanArchive, ModelCleanPlan, ModelCleanScene,
    plan_model_clean, validate_model_clean_archive,
    validate_model_clean_result,
)


class ModelCleanHost(Protocol):
    def capture_model_clean_scene(self) -> ModelCleanScene: ...
    def stage_model_clean_archive(self, plan: ModelCleanPlan) -> ModelCleanArchive:
        """Write OBJ, UV, material and attribute artifacts without replacing the scene."""
        ...
    def inspect_model_clean_archive(
        self, archive: ModelCleanArchive,
    ) -> ModelCleanArchive:
        """Independently read the staged files and their content digests."""
        ...
    def recoverable_scene_replacement(
        self, plan: ModelCleanPlan, archive: ModelCleanArchive,
    ) -> AbstractContextManager[None]:
        """Restore the original scene if replacement or verification fails."""
        ...
    def replace_scene_from_model_clean_archive(
        self, plan: ModelCleanPlan, archive: ModelCleanArchive,
    ) -> None: ...
    def release_model_clean_archive(self, archive: ModelCleanArchive) -> None: ...


@dataclass(frozen=True, slots=True)
class ModelCleanResult:
    plan: ModelCleanPlan
    archive: ModelCleanArchive
    scene: ModelCleanScene


class CleanModel:
    def __init__(self, host: ModelCleanHost) -> None:
        self._host = host

    def plan(self) -> ModelCleanPlan:
        return plan_model_clean(self._host.capture_model_clean_scene())

    def execute(self) -> ModelCleanResult:
        plan = self.plan()
        archive = self._host.stage_model_clean_archive(plan)
        try:
            inspected = self._host.inspect_model_clean_archive(archive)
            if inspected != archive:
                raise RuntimeError("Model Clean 归档在校验前发生变化")
            validate_model_clean_archive(plan, inspected)
            with self._host.recoverable_scene_replacement(plan, inspected):
                self._host.replace_scene_from_model_clean_archive(plan, inspected)
                scene = self._host.capture_model_clean_scene()
                validate_model_clean_result(plan, scene)
            return ModelCleanResult(plan, inspected, scene)
        finally:
            self._host.release_model_clean_archive(archive)
