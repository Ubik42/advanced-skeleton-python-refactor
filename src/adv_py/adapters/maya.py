from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import importlib.util
from typing import Iterable, Iterator

from adv_py.core.matrix import almost_equal, matrix44, transpose_flat
from adv_py.core.model import ConstraintSpec, NodeSpec, RigPlan


@dataclass(frozen=True, slots=True)
class MayaAdapterStatus:
    available: bool
    implementation: str = "basic-rig-host"
    responsibility: str = "DAG、joint、基础约束、事务清理与场景复检"

    @classmethod
    def detect(cls) -> "MayaAdapterStatus":
        return cls(available=importlib.util.find_spec("maya") is not None)


class MayaRigHost:
    """Minimal real Maya adapter for the portable node/constraint slice."""

    name = "maya"

    def __init__(self) -> None:
        from maya import cmds  # type: ignore[import-not-found]

        self._cmds = cmds
        self._nodes: dict[str, str] = {}
        self._constraints: list[str] = []
        self._active_created: list[str] | None = None
        self._last_created: tuple[str, ...] = ()

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        if self._active_created is not None:
            raise RuntimeError("MayaRigHost 不支持嵌套事务")
        self._active_created = []
        self._cmds.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        except Exception:
            self._delete_existing(reversed(self._active_created))
            raise
        else:
            self._last_created = tuple(self._active_created)
        finally:
            self._cmds.undoInfo(closeChunk=True)
            self._active_created = None

    def preflight(self, plan: RigPlan) -> tuple[str, ...]:
        errors = [
            f"场景中已存在节点 {node.name!r}"
            for node in plan.nodes
            if self._cmds.objExists(node.name)
        ]
        supported = {"parent", "point", "orient", "scale"}
        errors.extend(
            f"Maya 尚不支持约束 {constraint.kind!r}"
            for constraint in plan.constraints
            if constraint.kind not in supported
        )
        return tuple(errors)

    def create_node(self, node: NodeSpec) -> None:
        maya_type = "joint" if node.kind == "joint" else "transform"
        created = self._cmds.createNode(maya_type, name=node.name)
        self._cmds.xform(
            created,
            worldSpace=True,
            matrix=list(transpose_flat(node.world_matrix)),
        )
        if node.kind == "joint":
            self._cmds.makeIdentity(created, apply=True, rotate=True)
        elif node.kind == "control":
            self._cmds.addAttr(created, longName="portableRigControl", attributeType="bool")
            self._cmds.setAttr(f"{created}.portableRigControl", True)
        self._nodes[node.key] = created
        self._remember(created)

    def parent_node(self, child_key: str, parent_key: str) -> None:
        self._cmds.parent(
            self._nodes[child_key],
            self._nodes[parent_key],
            absolute=True,
        )

    def create_constraint(self, constraint: ConstraintSpec) -> None:
        commands = {
            "parent": self._cmds.parentConstraint,
            "point": self._cmds.pointConstraint,
            "orient": self._cmds.orientConstraint,
            "scale": self._cmds.scaleConstraint,
        }
        sources = [self._nodes[key] for key in constraint.sources]
        created = commands[constraint.kind](
            *sources,
            self._nodes[constraint.target],
            maintainOffset=constraint.maintain_offset,
        )[0]
        self._constraints.append(created)
        self._remember(created)

    def verify(self, plan: RigPlan) -> tuple[str, ...]:
        errors: list[str] = []
        for node in plan.nodes:
            maya_node = self._nodes.get(node.key)
            if not maya_node or not self._cmds.objExists(maya_node):
                errors.append(f"缺少节点 {node.key!r}")
                continue
            actual = matrix44(
                self._cmds.xform(maya_node, query=True, worldSpace=True, matrix=True)
            )
            actual = transpose_flat(actual)
            if not almost_equal(actual, node.world_matrix, tolerance=1e-4):
                errors.append(f"节点 {node.key!r} 的世界矩阵不一致")
            parents = self._cmds.listRelatives(maya_node, parent=True) or []
            expected_parent = self._nodes[node.parent] if node.parent else None
            actual_parent = parents[0] if parents else None
            if actual_parent != expected_parent:
                errors.append(f"节点 {node.key!r} 的父级不一致")
        for constraint in self._constraints:
            if not self._cmds.objExists(constraint):
                errors.append(f"缺少约束 {constraint!r}")
        return tuple(errors)

    def rollback_last(self) -> None:
        if not self._last_created:
            raise RuntimeError("没有可回滚的 Maya 构建事务")
        self._delete_existing(reversed(self._last_created))
        self._nodes.clear()
        self._constraints.clear()
        self._last_created = ()

    def _remember(self, node: str) -> None:
        if self._active_created is None:
            raise RuntimeError("场景修改必须发生在事务内")
        self._active_created.append(node)

    def _delete_existing(self, nodes: Iterable[str]) -> None:
        existing = [node for node in nodes if self._cmds.objExists(node)]
        if existing:
            self._cmds.delete(existing)
