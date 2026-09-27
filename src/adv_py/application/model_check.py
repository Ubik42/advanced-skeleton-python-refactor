"""Read-only Preparation / Model Check workflow."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.model_checker import (
    MODEL_SYMMETRY_TOLERANCE, ModelCheckGate, ModelCheckResult,
    ModelHistoryNode, ModelSymmetryIssue, ModelTransformState,
    inspect_model_history, inspect_model_symmetry,
    inspect_model_transforms,
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
    """Inspect each stage only after the preceding Continue decision."""

    def __init__(self, host: ModelCheckReviewHost) -> None:
        self.host = host

    def execute(self, *, game_engine: bool = False,
                skip_symmetry: bool = False) -> ModelCheckResult:
        if type(skip_symmetry) is not bool:
            raise ValueError("跳过模型对称检查必须是布尔值")
        mesh = self.host.selected_mesh()
        states = self.host.transform_chain(mesh)
        transforms = inspect_model_transforms(states)
        for state in states:
            issues = tuple(issue for issue in transforms
                           if issue.path == state.path)
            if issues and not self.host.confirm_model_check_gate(
                    ModelCheckGate("transform", state.path, issues)):
                raise ModelCheckCancelled("模型检查在 transform 阶段取消")

        history = inspect_model_history(self.host.history(mesh),
                                        game_engine=game_engine)
        if history and not self.host.confirm_model_check_gate(
                ModelCheckGate("history", mesh, history)):
            raise ModelCheckCancelled("模型检查在 history 阶段取消")

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
            if symmetry:
                self.host.select_asymmetric_vertices(mesh, symmetry)
                if not self.host.confirm_model_check_gate(
                        ModelCheckGate("symmetry", mesh, symmetry)):
                    raise ModelCheckCancelled("模型检查在 symmetry 阶段取消")
        return ModelCheckResult(mesh, vertex_count, transforms, history,
                                symmetry, not skip_symmetry)
