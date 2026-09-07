from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_weight_geometry import (
    SkinMeshGeometryState,
    SkinWeightGeometryMirrorRequest,
    SkinWeightMirrorDirection,
    plan_skin_weight_geometry_pairs,
    skin_weight_geometry_mirror_request,
)
from adv_py.core.skin_weight_io import SkinWeightInfluenceMapping
from adv_py.core.skin_weight_mirror import SkinWeightVertexPair
from adv_py.core.skin_weights import SkinWeightIssue

from .skin_weight_mirror import (
    MirrorSkinWeights,
    SkinWeightMirrorHost,
    SkinWeightMirrorPlan,
    SkinWeightMirrorResult,
)


class SkinWeightGeometryMirrorHost(SkinWeightMirrorHost, Protocol):
    def capture_mesh_vertex_positions(self, mesh_path: str) -> SkinMeshGeometryState: ...


@dataclass(frozen=True, slots=True)
class SkinWeightGeometryMirrorPlan:
    request: SkinWeightGeometryMirrorRequest
    geometry_state: SkinMeshGeometryState
    vertex_pairs: tuple[SkinWeightVertexPair, ...]
    geometry_issues: tuple[SkinWeightIssue, ...]
    mirror_plan: SkinWeightMirrorPlan | None

    @property
    def ready(self) -> bool:
        return not self.geometry_issues and self.mirror_plan is not None and self.mirror_plan.ready

    @property
    def blockers(self) -> tuple[str, ...]:
        issues = self.geometry_issues
        if self.mirror_plan is not None:
            issues += self.mirror_plan.input_issues
        return tuple(
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in issues
        )


@dataclass(frozen=True, slots=True)
class SkinWeightGeometryMirrorResult:
    plan: SkinWeightGeometryMirrorPlan
    mirror_result: SkinWeightMirrorResult


class MirrorSkinWeightsByGeometry:
    """Mirror weights after exact world-space vertex pairing across an X plane."""

    def __init__(self, host: SkinWeightGeometryMirrorHost) -> None:
        self._host = host
        self._mirror = MirrorSkinWeights(host)

    def plan(
        self,
        skin_name: str,
        mesh_path: str,
        direction: SkinWeightMirrorDirection,
        influences: tuple[SkinWeightInfluenceMapping, ...],
        *,
        plane_origin_x: float = 0.0,
        tolerance: float = 1e-5,
    ) -> SkinWeightGeometryMirrorPlan:
        request = skin_weight_geometry_mirror_request(
            skin_name,
            mesh_path,
            direction,
            influences,
            plane_origin_x=plane_origin_x,
            tolerance=tolerance,
        )
        geometry = self._host.capture_mesh_vertex_positions(request.mesh_path)
        pairs, issues = plan_skin_weight_geometry_pairs(request, geometry)
        mirror_plan = None
        if not issues:
            mirror_plan = self._mirror.plan(
                request.skin_name,
                request.mesh_path,
                pairs,
                request.influences,
            )
        return SkinWeightGeometryMirrorPlan(
            request,
            geometry,
            pairs,
            issues,
            mirror_plan,
        )

    def apply(
        self,
        skin_name: str,
        mesh_path: str,
        direction: SkinWeightMirrorDirection,
        influences: tuple[SkinWeightInfluenceMapping, ...],
        *,
        plane_origin_x: float = 0.0,
        tolerance: float = 1e-5,
    ) -> SkinWeightGeometryMirrorResult:
        plan = self.plan(
            skin_name,
            mesh_path,
            direction,
            influences,
            plane_origin_x=plane_origin_x,
            tolerance=tolerance,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "几何权重镜像预检失败，场景未修改：" + "；".join(plan.blockers)
            )
        assert plan.mirror_plan is not None
        current_geometry = self._host.capture_mesh_vertex_positions(plan.request.mesh_path)
        if current_geometry != plan.geometry_state:
            raise FitSkeletonValidationError("几何权重镜像的顶点位置在执行前发生变化")
        current_source = self._host.capture_skin_vertices(
            plan.request.skin_name,
            plan.request.mesh_path,
            tuple(pair.source_index for pair in plan.vertex_pairs),
        )
        current_target = self._host.capture_skin_vertices(
            plan.request.skin_name,
            plan.request.mesh_path,
            tuple(pair.target_index for pair in plan.vertex_pairs),
        )
        if (
            current_source != plan.mirror_plan.source_state
            or current_target != plan.mirror_plan.target_state
        ):
            raise FitSkeletonValidationError("几何权重镜像的权重在执行前发生变化")
        result = self._mirror.apply(
            plan.request.skin_name,
            plan.request.mesh_path,
            plan.vertex_pairs,
            plan.request.influences,
        )
        return SkinWeightGeometryMirrorResult(plan, result)
