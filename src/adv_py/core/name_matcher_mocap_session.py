"""Immutable boundary for a connected NameMatcher MoCap session."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NameMatcherMocapConstraint:
    node: str
    uuid: str
    control: str
    control_uuid: str
    kind: str


@dataclass(frozen=True, slots=True)
class NameMatcherMocapSession:
    group: str
    group_uuid: str
    constraints: tuple[NameMatcherMocapConstraint, ...]

    @property
    def controls(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.control for item in self.constraints))
