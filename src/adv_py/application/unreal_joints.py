"""Transactional create/delete for the original generic Unreal IK joints."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.unreal_joints import UnrealJointPlan, UnrealJointSpec, plan_unreal_joints


class UnrealJointsHost(Protocol):
    def capture_unreal_inputs(self) -> tuple[bool, bool, dict[str, bool]]: ...
    def preflight_unreal_joints(self, plan: UnrealJointPlan) -> None: ...
    def transaction(self, label: str): ...
    def delete_unreal_joints(self) -> None: ...
    def create_unreal_root(self, *, opm: bool) -> None: ...
    def create_unreal_marker(self, spec: UnrealJointSpec) -> None: ...
    def capture_unreal_hierarchy(self) -> dict[str, str]: ...


class CreateUnrealJoints:
    def __init__(self, host: UnrealJointsHost):
        self._host = host

    def apply(self) -> UnrealJointPlan:
        motion, opm, landmarks = self._host.capture_unreal_inputs()
        plan = plan_unreal_joints(has_root_motion=motion, opm=opm,
                                  landmarks=landmarks)
        self._host.preflight_unreal_joints(plan)
        with self._host.transaction("创建 Unreal Joints"):
            self._host.delete_unreal_joints()
            if plan.create_root:
                self._host.create_unreal_root(opm=plan.opm)
            for spec in plan.joints:
                self._host.create_unreal_marker(spec)
            hierarchy = self._host.capture_unreal_hierarchy()
            if any(hierarchy.get(spec.name) != spec.parent
                   for spec in plan.joints):
                raise RuntimeError("Unreal Joints 层级复检失败")
        return plan


class DeleteUnrealJoints:
    def __init__(self, host: UnrealJointsHost):
        self._host = host

    def apply(self) -> None:
        with self._host.transaction("删除 Unreal Joints"):
            self._host.delete_unreal_joints()
            if self._host.capture_unreal_hierarchy():
                raise RuntimeError("Unreal Joints 删除复检失败")
