from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_weight_io import (
    SkinWeightDocument, SkinWeightInfluenceMapping,
    raw_skin_document_changed_vertices, skin_weight_document_from_state,
)
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
    RawSkinWeightEditResult,
)


class SkinWeightMirrorHost(SkinWeightHost, Protocol):
    def capture_all_skin_weights(self, skin_name: str,
                                 mesh_path: str) -> SkinWeightInputState: ...
    def preflight_raw_skin_document(self, document: SkinWeightDocument) -> None: ...
    def apply_raw_skin_document(self, document: SkinWeightDocument) -> None: ...
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
    raw_document: SkinWeightDocument | None = None
    full_target_state: SkinWeightInputState | None = None

    @property
    def ready(self) -> bool:
        return not self.input_issues and (self.edit_plan is not None
                                          or self.raw_document is not None)

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in self.input_issues
        )


@dataclass(frozen=True, slots=True)
class SkinWeightMirrorResult:
    plan: SkinWeightMirrorPlan
    edit_result: SkinWeightEditResult | RawSkinWeightEditResult


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
        raw_document = None
        full_target = None
        if not issues:
            target_weights = plan_skin_weight_mirror(request, source, target)
            raw = source.normalization_mode in (0, 2) or any(
                not vertex.weights or abs(sum(entry.weight for entry in
                    vertex.weights) - 1.0) > 1e-6
                for vertex in source.vertices)
            if raw:
                full_target = self._host.capture_all_skin_weights(
                    request.skin_name, request.mesh_path)
                by_index = {vertex.vertex_index: vertex
                            for vertex in target_weights}
                merged = tuple(by_index.get(vertex.vertex_index, vertex)
                               for vertex in full_target.vertices)
                merged_state = SkinWeightInputState(
                    full_target.skin_name, full_target.geometry_path,
                    full_target.vertex_count, full_target.influence_paths,
                    full_target.locked_influences,
                    full_target.maximum_influences,
                    full_target.maintain_maximum_influences, merged,
                    full_target.normalization_mode)
                raw_document = skin_weight_document_from_state(
                    merged_state, preserve_raw=True)
                self._host.preflight_raw_skin_document(raw_document)
            else:
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
            raw_document,
            full_target,
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
        if plan.raw_document is None:
            result = self._editor.apply(
                plan.request.skin_name,
                plan.request.mesh_path,
                plan.edit_plan.request.vertices,
            )
        else:
            with self._host.transaction("镜像原始 Skin 权重"):
                full = self._host.capture_all_skin_weights(
                    plan.request.skin_name, plan.request.mesh_path)
                if full != plan.full_target_state:
                    raise FitSkeletonValidationError(
                        "权重镜像目标在执行前发生变化")
                changed = raw_skin_document_changed_vertices(
                    plan.raw_document, full)
                self._host.apply_raw_skin_document(plan.raw_document)
                result = RawSkinWeightEditResult(changed)
        return SkinWeightMirrorResult(plan, result)
