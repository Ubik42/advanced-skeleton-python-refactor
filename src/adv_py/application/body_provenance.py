from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_skeleton import (
    BodySkeletonIssue,
    BodySkeletonProvenance,
    BodySkeletonSnapshot,
    audit_body_provenance,
    oriented_body_provenance,
)


class BodyProvenanceHost(Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyProvenanceAudit:
    expected: BodySkeletonProvenance
    snapshot: BodySkeletonSnapshot
    issues: tuple[BodySkeletonIssue, ...]

    @property
    def owned(self) -> bool:
        return not self.issues


class InspectBodySkeletonProvenance:
    """Read and audit Python ownership metadata without modifying the scene."""

    def __init__(self, host: BodyProvenanceHost) -> None:
        self._host = host

    def execute(
        self,
        *,
        root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        expected_joint_count: int = 30,
    ) -> BodyProvenanceAudit:
        expected = oriented_body_provenance(
            source_container,
            expected_joint_count,
        )
        snapshot = self._host.capture_body_skeleton(root_name)
        return BodyProvenanceAudit(
            expected,
            snapshot,
            audit_body_provenance(expected, snapshot.provenance),
        )
