"""Read-only Preparation / Model Check workflow."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.model_checker import (
    MODEL_SYMMETRY_TOLERANCE, ModelCheckResult, ModelHistoryNode,
    ModelSymmetryIssue, ModelTransformState, inspect_model_history,
    inspect_model_symmetry, inspect_model_transforms,
)


class ModelCheckHost(Protocol):
    def selected_mesh(self) -> str: ...
    def transform_chain(self, mesh: str) -> tuple[ModelTransformState, ...]: ...
    def history(self, mesh: str) -> tuple[ModelHistoryNode, ...]: ...
    def symmetry_samples(self, mesh: str, tolerance: float) -> tuple[
        tuple[tuple[float, float, float], ...], tuple[int, ...]]: ...
    def select_asymmetric_vertices(
        self, mesh: str, issues: tuple[ModelSymmetryIssue, ...]
    ) -> None: ...


class CheckModel:
    def __init__(self, host: ModelCheckHost):
        self.host = host

    def execute(self, *, game_engine: bool = False,
                select_issues: bool = True) -> ModelCheckResult:
        mesh = self.host.selected_mesh()
        transforms = inspect_model_transforms(self.host.transform_chain(mesh))
        history = inspect_model_history(self.host.history(mesh),
                                        game_engine=game_engine)
        points, nearest = self.host.symmetry_samples(
            mesh, MODEL_SYMMETRY_TOLERANCE)
        symmetry = inspect_model_symmetry(points, nearest)
        result = ModelCheckResult(mesh, len(points), transforms, history, symmetry)
        if select_issues and symmetry:
            self.host.select_asymmetric_vertices(mesh, symmetry)
        return result
