from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_weight_io import SkinWeightInfluenceMapping
from adv_py.core.skin_weight_mirror import (
    SkinWeightMirrorRequest,
    SkinWeightVertexPair,
    audit_skin_weight_mirror_input,
    plan_skin_weight_mirror,
    skin_weight_mirror_request,
)
from adv_py.core.skin_weights import (
    SkinWeightInputState,
    SkinWeightIssue,
)

from .skin_weights import (
    EditSkinWeights,
    SkinWeightEditPlan,
    SkinWeightEditResult,
    SkinWeightHost,
)


class SkinWeightMirrorHost(SkinWeightHost, Protocol):
    def capture_skin_vertices(
        self,
        skin_name: str,
        mesh_path: str,
        vertex_indices: tuple[int, ...],
    ) -> SkinWeightInputState: ...


@dataclass(frozen=True, slots=True)
class SkinWeightMirrorPlan:
    request: SkinWeightMirrorRequest
    source_state: SkinWeightInputState
    target_state: SkinWeightInputState
    input_issues: tuple[SkinWeightIssue, ...]
    edit_plan: SkinWeightEditPlan | None

    @property
    def ready(self) -> bool:
        return not self.input_issues and self.edit_plan is not None

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in self.input_issues
        )


@dataclass(frozen=True, slots=True)
class SkinWeightMirrorResult:
    plan: SkinWeightMirrorPlan
    edit_result: SkinWeightEditResult


class MirrorSkinWeights:
    def __init__(self, host: SkinWeightMirrorHost) -> None:
        self._host = host
        self._editor = EditSkinWeights(host)

    def plan(
        self,
        skin_name: str,
        mesh_path: str,
        vertex_pairs: tuple[SkinWeightVertexPair, ...],
        influences: tuple[SkinWeightInfluenceMapping, ...],
    ) -> SkinWeightMirrorPlan:
        request = skin_weight_mirror_request(
            skin_name,
            mesh_path,
            vertex_pairs,
            influences,
        )
        source_indices = tuple(pair.source_index for pair in request.vertex_pairs)
        target_indices = tuple(pair.target_index for pair in request.vertex_pairs)
        source = self._host.capture_skin_vertices(
            request.skin_name,
            request.mesh_path,
            source_indices,
        )
        target = self._host.capture_skin_vertices(
            request.skin_name,
            request.mesh_path,
            target_indices,
        )
        issues = audit_skin_weight_mirror_input(request, source, target)
        edit_plan = None
        if not issues:
            target_weights = plan_skin_weight_mirror(request, source, target)
            edit_plan = self._editor.plan(
                request.skin_name,
                request.mesh_path,
                target_weights,
            )
            issues = edit_plan.input_issues
        return SkinWeightMirrorPlan(
            request,
            source,
            target,
            issues,
            edit_plan,
        )

    def apply(
        self,
        skin_name: str,
        mesh_path: str,
        vertex_pairs: tuple[SkinWeightVertexPair, ...],
        influences: tuple[SkinWeightInfluenceMapping, ...],
    ) -> SkinWeightMirrorResult:
        plan = self.plan(
            skin_name,
            mesh_path,
            vertex_pairs,
            influences,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "权重镜像预检失败，场景未修改："
                + "；".join(plan.blockers)
            )
        source_indices = tuple(
            pair.source_index for pair in plan.request.vertex_pairs
        )
        target_indices = tuple(
            pair.target_index for pair in plan.request.vertex_pairs
        )
        current_source = self._host.capture_skin_vertices(
            plan.request.skin_name,
            plan.request.mesh_path,
            source_indices,
        )
        current_target = self._host.capture_skin_vertices(
            plan.request.skin_name,
            plan.request.mesh_path,
            target_indices,
        )
        if (
            current_source != plan.source_state
            or current_target != plan.target_state
        ):
            raise FitSkeletonValidationError("权重镜像场景在执行前发生变化")
        result = self._editor.apply(
            plan.request.skin_name,
            plan.request.mesh_path,
            plan.edit_plan.request.vertices,
        )
        return SkinWeightMirrorResult(plan, result)
