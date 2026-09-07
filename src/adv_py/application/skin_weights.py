from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_weights import (
    SkinVertexWeights,
    SkinWeightChange,
    SkinWeightEditRequest,
    SkinWeightInputState,
    SkinWeightIssue,
    audit_skin_weight_input,
    audit_skin_weight_result,
    plan_skin_weight_changes,
    skin_weight_request,
)


class SkinWeightHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_skin_weight_input(self, request: SkinWeightEditRequest) -> SkinWeightInputState: ...
    def apply_skin_weight_changes(self, request: SkinWeightEditRequest, changes: tuple[SkinWeightChange, ...]) -> None: ...


@dataclass(frozen=True, slots=True)
class SkinWeightEditPlan:
    request: SkinWeightEditRequest
    input_state: SkinWeightInputState
    input_issues: tuple[SkinWeightIssue, ...]
    changes: tuple[SkinWeightChange, ...]

    @property
    def ready(self) -> bool:
        return not self.input_issues

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in self.input_issues
        )


@dataclass(frozen=True, slots=True)
class SkinWeightEditResult:
    plan: SkinWeightEditPlan
    snapshot: SkinWeightInputState

    @property
    def changed_vertex_count(self) -> int:
        return len(self.plan.changes)


class EditSkinWeights:
    """Replace complete non-zero influence weights on explicit vertices."""

    def __init__(self, host: SkinWeightHost) -> None:
        self._host = host

    def plan(
        self,
        skin_name: str,
        mesh_path: str,
        vertices: tuple[SkinVertexWeights, ...],
    ) -> SkinWeightEditPlan:
        request = skin_weight_request(skin_name, mesh_path, vertices)
        state = self._host.capture_skin_weight_input(request)
        issues = audit_skin_weight_input(request, state)
        changes = plan_skin_weight_changes(request, state) if not issues else ()
        return SkinWeightEditPlan(request, state, issues, changes)

    def apply(
        self,
        skin_name: str,
        mesh_path: str,
        vertices: tuple[SkinVertexWeights, ...],
    ) -> SkinWeightEditResult:
        plan = self.plan(skin_name, mesh_path, vertices)
        if not plan.ready:
            raise FitSkeletonValidationError(
                "权重编辑预检失败，场景未修改：" + "；".join(plan.blockers)
            )
        if not plan.changes:
            return SkinWeightEditResult(plan, plan.input_state)
        with self._host.transaction("写入显式顶点权重"):
            current = self._host.capture_skin_weight_input(plan.request)
            if current != plan.input_state or audit_skin_weight_input(plan.request, current):
                raise FitSkeletonValidationError("权重编辑输入在执行前发生变化")
            self._host.apply_skin_weight_changes(plan.request, plan.changes)
            snapshot = self._host.capture_skin_weight_input(plan.request)
            issues = audit_skin_weight_result(plan.request, snapshot)
            if issues:
                raise RuntimeError(
                    "权重编辑后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
        return SkinWeightEditResult(plan, snapshot)
