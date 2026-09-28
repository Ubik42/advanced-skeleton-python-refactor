"""Create original-style ControlSet and DeformSet with the character."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_selection_sets import (
    BodySelectionSetsPlan, plan_body_selection_sets,
)
from adv_py.core.character_registry import CharacterRegistration


class BodySelectionSetsHost(Protocol):
    def resolve_body_selection_members(
        self, registration: CharacterRegistration,
        segments: tuple[str, ...], extras: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]: ...

    def preflight_body_selection_sets(
        self, plan: BodySelectionSetsPlan,
    ) -> None: ...

    def create_body_selection_sets(
        self, plan: BodySelectionSetsPlan,
    ) -> None: ...

    def capture_body_selection_sets(
        self, plan: BodySelectionSetsPlan,
    ) -> BodySelectionSetsPlan: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class BuildBodySelectionSets:
    def __init__(self, host: BodySelectionSetsHost) -> None:
        self._host = host

    def apply(self, registration: CharacterRegistration,
              segments: tuple[str, ...] = (), *,
              extras: tuple[str, ...] = ()) -> BodySelectionSetsPlan:
        controls, joints = self._host.resolve_body_selection_members(
            registration, segments, extras)
        pose_channels = tuple((channel.node, channel.attribute)
                              for channel in registration.channels
                              if channel.key.startswith("fitpart."))
        plan = plan_body_selection_sets(
            controls, joints, pose_channels)
        self._host.preflight_body_selection_sets(plan)
        with self._host.transaction("创建角色控制与变形选择集"):
            self._host.create_body_selection_sets(plan)
            actual = self._host.capture_body_selection_sets(plan)
            if set(actual.controls) != set(plan.controls) or set(
                    actual.deform_joints) != set(plan.deform_joints):
                raise RuntimeError("角色选择集成员读回不一致")
        return plan
