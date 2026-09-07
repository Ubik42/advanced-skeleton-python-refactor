from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import Iterator

from adv_py.core.model import ConstraintSpec, NodeSpec, RigPlan


@dataclass(slots=True)
class _MemoryNode:
    spec: NodeSpec
    parent: str | None = None


class InMemoryRigHost:
    """Deterministic adapter for testing portable orchestration outside any DCC."""

    name = "memory"

    def __init__(self) -> None:
        self.nodes: dict[str, _MemoryNode] = {}
        self.constraints: list[ConstraintSpec] = []
        self._last_snapshot: tuple[dict[str, _MemoryNode], list[ConstraintSpec]] | None = None

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        del label
        nodes_before = deepcopy(self.nodes)
        constraints_before = list(self.constraints)
        try:
            yield
        except Exception:
            self.nodes = nodes_before
            self.constraints = constraints_before
            raise
        else:
            self._last_snapshot = (nodes_before, constraints_before)

    def preflight(self, plan: RigPlan) -> tuple[str, ...]:
        conflicts = [node.name for node in plan.nodes if any(item.spec.name == node.name for item in self.nodes.values())]
        return tuple(f"场景中已存在节点 {name!r}" for name in conflicts)

    def create_node(self, node: NodeSpec) -> None:
        if node.key in self.nodes:
            raise RuntimeError(f"重复创建节点 key：{node.key}")
        self.nodes[node.key] = _MemoryNode(spec=node)

    def parent_node(self, child_key: str, parent_key: str) -> None:
        self.nodes[child_key].parent = parent_key

    def create_constraint(self, constraint: ConstraintSpec) -> None:
        self.constraints.append(constraint)

    def verify(self, plan: RigPlan) -> tuple[str, ...]:
        errors: list[str] = []
        for node in plan.nodes:
            actual = self.nodes.get(node.key)
            if actual is None:
                errors.append(f"缺少节点 {node.key!r}")
            elif actual.parent != node.parent:
                errors.append(f"节点 {node.key!r} 的父级不一致")
        if len(self.constraints) < len(plan.constraints):
            errors.append("约束数量不足")
        return tuple(errors)

    def rollback_last(self) -> None:
        if self._last_snapshot is None:
            raise RuntimeError("没有可回滚的构建事务")
        self.nodes, self.constraints = self._last_snapshot
        self._last_snapshot = None
