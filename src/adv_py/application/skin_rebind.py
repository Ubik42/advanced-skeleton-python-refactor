"""Replace a stale Skin and project a captured source asset in one transaction."""
from __future__ import annotations

from dataclasses import dataclass
from array import array

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_bind import (
    SkinBindMethod, SkinWeightNormalization, SkinningMethod,
    SkinWeightDistribution,
    GeodesicBindPreferences,
    audit_skin_bind_result, plan_skin_bind,
)
from adv_py.core.skin_weight_surface_source import SkinWeightSurfaceSource
from adv_py.core.skin_weight_io import raw_skin_document_changed_vertices

from .skin_weight_surface_transfer import TransferSkinWeightsBySurface
from .skin_weights import EditSkinWeights


@dataclass(frozen=True, slots=True)
class SkinRebindState:
    skin: str
    mesh: str
    influences: tuple[str, ...]
    maximum_influences: int
    maintain_maximum_influences: bool
    bind_method: SkinBindMethod
    normalization: SkinWeightNormalization
    skinning_method: SkinningMethod
    weight_distribution: SkinWeightDistribution
    envelope: float
    envelope_source: str | None
    set_memberships: tuple[str, ...]
    old_topology: str
    current_topology: str
    geom_bind_node: str | None = None
    geodesic: GeodesicBindPreferences | None = None
    geom_bind_members: tuple[str, ...] = ()
    locked_influences: tuple[str, ...] = ()
    deformer_settings: tuple[tuple[str, float, str | None], ...] = ()
    bind_pre_matrices: tuple[tuple[str, tuple[float, ...], str | None], ...] = ()


@dataclass(frozen=True, slots=True)
class SkinRebindResult:
    vertices: int
    changed_vertices: int
    maximum_distance: float


class RebindSkinFromSurfaceSource:
    def __init__(self, host) -> None:
        self._host = host

    def apply(self, source: SkinWeightSurfaceSource, skin: str, mesh: str,
              *, max_distance: float,
              max_discarded_weight: float = 0.000001) -> SkinRebindResult:
        state = self._host.capture_skin_rebind_state(skin, mesh)
        if state.old_topology == state.current_topology:
            raise FitSkeletonValidationError("目标 Skin 的拓扑没有变化，无需重绑")
        if source.bind_topology != state.old_topology:
            raise FitSkeletonValidationError(
                "源资产的绑定拓扑与旧 Skin 不一致；请从原拓扑重新导出来源")
        if (source.weights.skin_name != skin or source.weights.mesh_path != mesh):
            raise FitSkeletonValidationError("源资产的 Skin 或网格路径与目标不一致")
        if set(source.weights.influence_paths) != set(state.influences):
            raise FitSkeletonValidationError("源资产的影响关节与当前 Skin 不一致")
        if (source.weights.maximum_influences != state.maximum_influences
                or source.weights.maintain_maximum_influences
                != state.maintain_maximum_influences):
            raise FitSkeletonValidationError("源资产的最大影响数设置与当前 Skin 不一致")
        if (not source.weights.normalized
                and state.normalization is SkinWeightNormalization.INTERACTIVE):
            raise FitSkeletonValidationError(
                "原始非归一化权重不能重绑到 Interactive Normalize Skin")
        if (state.skinning_method is SkinningMethod.WEIGHT_BLENDED
                and source.blend_weights is None):
            raise FitSkeletonValidationError(
                "Weight Blended 重绑需要含逐顶点混合权重的新版来源资产")
        if source.member_vertices is None:
            raise FitSkeletonValidationError(
                "拓扑重绑需要记录 Skin 变形集成员的新版来源资产")
        if not source.member_vertices:
            raise FitSkeletonValidationError("源 Skin 变形集没有受影响顶点")
        bind = plan_skin_bind(mesh, state.influences, skin_name=skin,
            maximum_influences=state.maximum_influences,
            maintain_maximum_influences=state.maintain_maximum_influences,
            bind_method=state.bind_method,
            normalization=state.normalization,
            skinning_method=state.skinning_method,
            weight_distribution=state.weight_distribution,
            geodesic=state.geodesic)
        with self._host.transaction("引用模型拓扑更新后重绑 Skin 并转移权重"):
            if self._host.capture_skin_rebind_state(skin, mesh) != state:
                raise FitSkeletonValidationError("目标 Skin 或模型在执行前发生变化")
            self._host.remove_skin_bind_for_rebind(skin)
            self._host.unlock_skin_rebind_influences(state)
            self._host.create_skin_bind(bind)
            bind_issues = audit_skin_bind_result(
                bind, self._host.capture_skin_bind(bind))
            if bind_issues:
                raise FitSkeletonValidationError(
                    "重绑 Skin 参数读回不一致："
                    + "；".join(issue.message for issue in bind_issues))
            self._host.restore_skin_rebind_deformer_state(state)
            transfer = TransferSkinWeightsBySurface(self._host).plan_from_documents(
                source.weights, source.geometry, skin, mesh,
                max_distance=max_distance,
                max_discarded_weight=max_discarded_weight,
                source_blend_weights=source.blend_weights,
                source_member_vertices=source.member_vertices)
            projected_weights = transfer.transfer.document
            if projected_weights.normalized:
                editor = EditSkinWeights(self._host)
                edit_plan = editor.plan(skin, mesh,
                                        projected_weights.vertices)
                changed_vertices = editor.apply_plan_in_transaction(
                    edit_plan).changed_vertex_count
            else:
                before_weights = self._host.capture_all_skin_weights(
                    skin, mesh)
                changed_vertices = raw_skin_document_changed_vertices(
                    projected_weights, before_weights)
                self._host.apply_raw_skin_document(projected_weights)
            if state.skinning_method is SkinningMethod.WEIGHT_BLENDED:
                projected = transfer.transfer.blend_weights
                if projected is None:
                    raise RuntimeError("Weight Blended 重绑未生成混合权重")
                self._host.apply_skin_blend_weights(skin, array("d", projected))
                restored = self._host.capture_skin_blend_weights(skin)
                if (len(restored) != len(projected)
                        or any(abs(actual - expected) > 1e-6
                               for actual, expected in zip(
                                   restored, projected))):
                    raise RuntimeError(
                        "Weight Blended 重绑混合权重未完整写回")
            projected_members = transfer.transfer.member_vertices
            if projected_members is None or not projected_members:
                raise FitSkeletonValidationError(
                    "表面投射没有生成可用的 Skin 变形集")
            self._host.apply_skin_vertex_membership(
                skin, mesh, projected_members)
            self._host.restore_skin_rebind_influences(state)
            return SkinRebindResult(transfer.transfer.document.vertex_count,
                changed_vertices,
                transfer.transfer.max_surface_distance)
