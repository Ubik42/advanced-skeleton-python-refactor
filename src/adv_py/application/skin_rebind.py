"""Replace a stale Skin and project a captured source asset in one transaction."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_bind import plan_skin_bind
from adv_py.core.skin_weight_surface_source import SkinWeightSurfaceSource

from .skin_weight_surface_transfer import TransferSkinWeightsBySurface
from .skin_weights import EditSkinWeights


@dataclass(frozen=True, slots=True)
class SkinRebindState:
    skin: str
    mesh: str
    influences: tuple[str, ...]
    maximum_influences: int
    maintain_maximum_influences: bool
    old_topology: str
    current_topology: str


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
        if (source.weights.skin_name != skin or source.weights.mesh_path != mesh):
            raise FitSkeletonValidationError("源资产的 Skin 或网格路径与目标不一致")
        if set(source.weights.influence_paths) != set(state.influences):
            raise FitSkeletonValidationError("源资产的影响关节与当前 Skin 不一致")
        if (source.weights.maximum_influences != state.maximum_influences
                or source.weights.maintain_maximum_influences
                != state.maintain_maximum_influences):
            raise FitSkeletonValidationError("源资产的最大影响数设置与当前 Skin 不一致")
        bind = plan_skin_bind(mesh, state.influences, skin_name=skin,
            maximum_influences=state.maximum_influences,
            maintain_maximum_influences=state.maintain_maximum_influences)
        with self._host.transaction("引用模型拓扑更新后重绑 Skin 并转移权重"):
            if self._host.capture_skin_rebind_state(skin, mesh) != state:
                raise FitSkeletonValidationError("目标 Skin 或模型在执行前发生变化")
            self._host.remove_skin_bind_for_rebind(skin)
            self._host.create_skin_bind(bind)
            self._host.capture_skin_bind(bind)
            transfer = TransferSkinWeightsBySurface(self._host).plan_from_documents(
                source.weights, source.geometry, skin, mesh,
                max_distance=max_distance,
                max_discarded_weight=max_discarded_weight)
            editor = EditSkinWeights(self._host)
            edit_plan = editor.plan(skin, mesh, transfer.transfer.document.vertices)
            edit = editor.apply_plan_in_transaction(edit_plan)
            return SkinRebindResult(transfer.transfer.document.vertex_count,
                edit.changed_vertex_count,
                transfer.transfer.max_surface_distance)
