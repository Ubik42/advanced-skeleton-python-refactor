from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_rebuild import (
    BodyRebuildIssue,
    BodyRebuildSceneState,
    audit_body_rebuild_safety,
)
from adv_py.core.body_skeleton import BodySkeletonSnapshot, oriented_body_provenance

from .fit_symmetry import FitSymmetryHost, FitSymmetryPlan, PlanFitSymmetry


class BodyRebuildInspectionHost(FitSymmetryHost, Protocol):
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...

    def capture_body_rebuild_state(
        self,
        root_name: str,
    ) -> BodyRebuildSceneState: ...


@dataclass(frozen=True, slots=True)
class BodyRebuildSafetyAudit:
    symmetry: FitSymmetryPlan
    body: BodySkeletonSnapshot
    scene: BodyRebuildSceneState
    issues: tuple[BodyRebuildIssue, ...]

    @property
    def safe_to_replace(self) -> bool:
        return not self.issues


class InspectBodyRebuildSafety:
    """Read the complete known replacement boundary without mutating Maya."""

    def __init__(self, host: BodyRebuildInspectionHost) -> None:
        self._host = host
        self._symmetry = PlanFitSymmetry(host)

    def execute(
        self,
        container_name: str = "FitSkeleton",
        *,
        root_name: str = "Root_M",
        center_tolerance: float = 0.01,
    ) -> BodyRebuildSafetyAudit:
        symmetry = self._symmetry.execute(
            container_name,
            center_tolerance=center_tolerance,
        )
        body = self._host.capture_body_skeleton(root_name)
        scene = self._host.capture_body_rebuild_state(root_name)
        provenance = oriented_body_provenance(
            symmetry.source.hierarchy.container,
            len(symmetry.instances),
        )
        return BodyRebuildSafetyAudit(
            symmetry,
            body,
            scene,
            audit_body_rebuild_safety(
                symmetry.instances,
                body,
                scene,
                provenance,
            ),
        )
