"""Move Fit joints and update the connected aim chain in one transaction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_orientation import (
    FitOrientationRequest,
    FitOrientationSnapshot,
    select_fit_orientation_child,
)
from adv_py.core.fit_position import FitJointPositionPatch

from .fit_orientation_auto import (
    FitOrientationAutoHost,
    FitOrientationAutoResult,
    OrientFitJoints,
)
from .fit_position import (
    EditFitJointPositions,
    FitPositionEditResult,
    FitPositionHost,
)


class OrientedFitPositionHost(FitPositionHost, FitOrientationAutoHost, Protocol):
    pass


@dataclass(frozen=True, slots=True)
class OrientedFitPositionResult:
    position: FitPositionEditResult
    orientation: FitOrientationAutoResult | NativeFitOrientationResult | None

    @property
    def plan(self):
        return self.position.plan


@dataclass(frozen=True,slots=True)
class NativeFitOrientationResult:
    aimed_parents: tuple[str,...]
    verified: FitOrientationSnapshot


class EditAndOrientFitJointPositions:
    """Match Fit Mode's position change followed by parent/child re-aim."""

    def __init__(self, host: OrientedFitPositionHost) -> None:
        self._host = host
        self._position = EditFitJointPositions(host)
        self._orientation = OrientFitJoints(host)

    def apply(
        self, patch: FitJointPositionPatch,
        container_name: str = "FitSkeleton",
    ) -> OrientedFitPositionResult:
        plan = self._position.plan(patch, container_name)
        if not plan.changes:
            return OrientedFitPositionResult(
                FitPositionEditResult(plan, plan.before_hierarchy), None
            )
        container = plan.before_hierarchy.container
        with self._host.transaction(
            f"移动并重新定向 {len(plan.changes)} 个 Fit joint"
        ):
            for change in plan.changes:
                self._host.set_fit_joint_local_position(
                    change.joint, change.after, change.changed_axes
                )
            moved = self._host.capture_fit_hierarchy(container)
            settings = self._host.read_fit_skeleton_settings(container)
            EditFitJointPositions._verify(plan, moved, settings)
            position = FitPositionEditResult(plan, moved)
            snapshot = self._host.capture_fit_orientation(container)
            native=getattr(self._host,'update_source_fit_orientations',None)
            if callable(native):
                from adv_py.core.source_fit_mode import source_fit_mode_selection
                selected=tuple(change.joint for change in plan.changes)
                dispatch=source_fit_mode_selection(snapshot,selected)
                applied=native(dispatch.aiming_children,container=container)
                verified=self._host.capture_fit_orientation(container)
                return OrientedFitPositionResult(position,
                    NativeFitOrientationResult(tuple(applied or ()),verified))
            nodes = {node.path: node for node in snapshot.hierarchy.joints}
            targets: set[str] = set()
            for change in plan.changes:
                current = change.joint
                if select_fit_orientation_child(snapshot, current) is not None:
                    targets.add(current)
                while (parent := nodes[current].dag_parent) in nodes:
                    if select_fit_orientation_child(snapshot, parent) != current:
                        break
                    targets.add(parent)
                    current = parent
            orientation = None
            if targets:
                request = FitOrientationRequest(tuple(sorted(
                    targets, key=lambda path: (path.count("|"), path)
                )))
                orientation_plan = self._orientation.plan(request, container)
                orientation = self._orientation.apply_plan_in_transaction(
                    orientation_plan
                )
        return OrientedFitPositionResult(position, orientation)
