"""Apply complete Skin weights by exact influence name and vertex index."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.dense_skin_transfer import (
    DenseSkinWeights, reorder_dense_skin, validate_dense_skin,
)


class DenseSkinHost(Protocol):
    def transaction(self, label: str): ...
    def capture_dense_skin(self, skin_name: str) -> DenseSkinWeights: ...
    def apply_dense_skin(self, data: DenseSkinWeights) -> None: ...


@dataclass(frozen=True, slots=True)
class DenseSkinTransferPlan:
    source: DenseSkinWeights
    target_before: DenseSkinWeights
    target_after: DenseSkinWeights


class TransferDenseSkinWeights:
    def __init__(self, host: DenseSkinHost):
        self._host = host

    def plan(self, source: DenseSkinWeights,
             target_skin: str) -> DenseSkinTransferPlan:
        validate_dense_skin(source)
        before = self._host.capture_dense_skin(target_skin)
        if before.vertex_count != source.vertex_count:
            raise ValueError("来源和目标网格顶点数不一致")
        after = reorder_dense_skin(source, target_skin,
                                   before.influence_names)
        return DenseSkinTransferPlan(source, before, after)

    def apply(self, source: DenseSkinWeights,
              target_skin: str) -> DenseSkinTransferPlan:
        plan = self.plan(source, target_skin)
        with self._host.transaction("迁移原版 Skin 全量权重"):
            if self._host.capture_dense_skin(target_skin) != plan.target_before:
                raise ValueError("目标 Skin 在权重迁移前发生变化")
            self._host.apply_dense_skin(plan.target_after)
            if self._host.capture_dense_skin(target_skin) != plan.target_after:
                raise RuntimeError("Skin 批量权重写后复检失败")
        return plan
