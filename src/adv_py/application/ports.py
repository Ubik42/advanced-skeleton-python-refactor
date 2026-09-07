from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.model import ConstraintSpec, NodeSpec, RigPlan


class RigHost(Protocol):
    """The minimum scene operations required by the first portable rig slice."""

    @property
    def name(self) -> str: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight(self, plan: RigPlan) -> tuple[str, ...]: ...

    def create_node(self, node: NodeSpec) -> None: ...

    def parent_node(self, child_key: str, parent_key: str) -> None: ...

    def create_constraint(self, constraint: ConstraintSpec) -> None: ...

    def verify(self, plan: RigPlan) -> tuple[str, ...]: ...

    def rollback_last(self) -> None: ...
