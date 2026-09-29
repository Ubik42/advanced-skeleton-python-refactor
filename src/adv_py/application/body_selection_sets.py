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


def unregistered_fk_selection_extras(
    registration: CharacterRegistration, rig_plan,
) -> tuple[str, ...]:
    """Keep locked FK curves selectable even without registered channels."""
    controls = (
        rig_plan.arm.fk_controls.controls
        + rig_plan.leg.fk_controls.controls
        + (rig_plan.hand.controls.controls
           if rig_plan.hand is not None else ())
        + (rig_plan.torso.torso.controls.controls
           if rig_plan.torso is not None else ())
    )
    registered = {channel.node for channel in registration.channels}
    return tuple(
        spec.extra_path or spec.control_path
        for spec in controls
        if spec.control_path not in registered
        and spec.control_path not in rig_plan.no_control_paths
    )


def finalize_body_character_sets(
    host, registration: CharacterRegistration, rig_plan, *,
    segments: tuple[str, ...] = (),
    extras: tuple[str, ...] = (),
    scene_before=None,
    fit_container: str = "FitSkeleton",
    create_sets: bool = True,
    populate_all: bool = True,
) -> None:
    """Finish ownership only after the last rig/Skin node has been created.

    Rebuild can defer this step until its legacy channels are reconciled.
    A skinned build creates the sets with the rig, then calls this function
    again after Skin binding with ``create_sets=False``.
    """
    if create_sets:
        BuildBodySelectionSets(host).apply(
            registration, segments,
            extras=extras + unregistered_fk_selection_extras(
                registration, rig_plan))
        if host.has_body_build_pose_overrides():
            from .body_build_pose import GoToBodyBuildPose
            GoToBodyBuildPose(host).apply()
    if populate_all:
        if scene_before is None:
            raise ValueError("登记 AllSet 需要构建前场景快照")
        from .body_all_set import PopulateBodyAllSet
        PopulateBodyAllSet(host).apply(scene_before, fit_container)
