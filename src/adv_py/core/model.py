from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .matrix import IDENTITY_MATRIX, Matrix44


NodeKind = Literal["joint", "transform", "control"]
ConstraintKind = Literal["parent", "point", "orient", "scale"]


@dataclass(frozen=True, slots=True)
class NodeSpec:
    """Host-independent identity and hierarchy for one rig node."""

    key: str
    name: str
    kind: NodeKind
    parent: str | None = None
    world_matrix: Matrix44 = IDENTITY_MATRIX
    extent: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConstraintSpec:
    """A semantic relationship; each host chooses its concrete implementation."""

    kind: ConstraintKind
    sources: tuple[str, ...]
    target: str
    maintain_offset: bool = True


@dataclass(frozen=True, slots=True)
class LimbSpec:
    """Host-independent three-joint IK/FK limb semantics."""

    key: str
    bind_chain: tuple[str, str, str]
    fk_chain: tuple[str, str, str]
    ik_chain: tuple[str, str, str]
    fk_controls: tuple[str, str, str]
    ik_target: str
    pole_vector: str
    settings: str
    blend_attribute: str = "ik_fk"


@dataclass(frozen=True, slots=True)
class RigPlan:
    """A declarative rig slice that can be validated before touching a DCC scene."""

    name: str
    nodes: tuple[NodeSpec, ...]
    constraints: tuple[ConstraintSpec, ...] = ()
    limbs: tuple[LimbSpec, ...] = ()
