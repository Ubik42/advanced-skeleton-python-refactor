"""Read-only Preparation / Model Check workflow."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.model_checker import (
    MODEL_SYMMETRY_TOLERANCE, ModelCheckGate, ModelCheckResult,
    ModelHistoryNode, ModelSymmetryIssue, ModelTransformState,
    inspect_model_history, inspect_model_symmetry,
    inspect_model_transforms, plan_model_check_gates,
)


class ModelCheckHost(Protocol):
    def selected_mesh(self) -> str: ...
    def vertex_count(self, mesh: str) -> int: ...
    def transform_chain(self, mesh: str) -> tuple[ModelTransformState, ...]: ...
    def history(self, mesh: str) -> tuple[ModelHistoryNode, ...]: ...
    def symmetry_samples(self, mesh: str, tolerance: float) -> tuple[
        tuple[tuple[float, float, float], ...], tuple[int, ...]]: ...
    def select_asymmetric_vertices(
        self, mesh: str, issues: tuple[ModelSymmetryIssue, ...]
    ) -> None: ...


class ModelCheckReviewHost(ModelCheckHost, Protocol):
    def confirm_model_check_gate(self, gate: ModelCheckGate) -> bool: ...


class ModelCheckCancelled(RuntimeError):
    pass


class CheckModel:
    def __init__(self, host: ModelCheckHost):
        self.host = host

    def execute(self, *, game_engine: bool = False,
                select_issues: bool = True,
                skip_symmetry: bool = False) -> ModelCheckResult:
        if type(skip_symmetry) is not bool:
            raise ValueError("跳过模型对称检查必须是布尔值")
        mesh = self.host.selected_mesh()
        transforms = inspect_model_transforms(self.host.transform_chain(mesh))
        history = inspect_model_history(self.host.history(mesh),
                                        game_engine=game_engine)
        if skip_symmetry:
            vertex_count = self.host.vertex_count(mesh)
            if vertex_count < 1:
                raise ValueError("所选模型没有可检查的顶点")
            symmetry = ()
        else:
            points, nearest = self.host.symmetry_samples(
                mesh, MODEL_SYMMETRY_TOLERANCE)
            vertex_count = len(points)
            symmetry = inspect_model_symmetry(points, nearest)
        result = ModelCheckResult(mesh, vertex_count, transforms, history,
                                  symmetry, not skip_symmetry)
        if select_issues and symmetry:
            self.host.select_asymmetric_vertices(mesh, symmetry)
        return result


class ReviewModelCheck:
    """Apply the original per-stage Continue/Cancel decisions after capture."""

    def __init__(self, host: ModelCheckReviewHost) -> None:
        self.host = host

    def execute(self, *, game_engine: bool = False,
                skip_symmetry: bool = False) -> ModelCheckResult:
        result = CheckModel(self.host).execute(
            game_engine=game_engine, select_issues=False,
            skip_symmetry=skip_symmetry)
        order = tuple(state.path for state in
                      self.host.transform_chain(result.mesh))
        for gate in plan_model_check_gates(result, order):
            if gate.category == "symmetry":
                self.host.select_asymmetric_vertices(
                    result.mesh, result.symmetry_issues)
            if not self.host.confirm_model_check_gate(gate):
                raise ModelCheckCancelled(
                    "模型检查在 " + gate.category + " 阶段取消")
        return result
