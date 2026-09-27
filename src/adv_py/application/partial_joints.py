"""ADV Partial Joints operations, independent of the Maya command layer."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.partial_joints import (
    PartialDeleteSpec, PartialJointCandidate, PartialJointSpec,
    plan_create_partial_joints, plan_delete_partial_joints,
)


class PartialJointsHost(Protocol):
    def capture_partial_candidates(self) -> tuple[PartialJointCandidate, ...]: ...
    def resolve_partial_selection(self) -> tuple[str, ...]: ...
    def preflight_partial_scene(self, *, include_controller: bool,
                                multi: bool, auto_bind: bool) -> None: ...
    def find_name_collisions(self, name: str): ...
    def transaction(self, label: str): ...
    def create_partial_joint(self, spec: PartialJointSpec) -> None: ...
    def delete_partial_joint(self, spec: PartialDeleteSpec) -> None: ...
    def capture_partial_presence(self, joint: str) -> tuple[bool, bool]: ...
    def remove_empty_partial_system(self) -> None: ...


class CreatePartialJoints:
    def __init__(self, host: PartialJointsHost):
        self._host = host

    def apply(self, *, count: int = 1, include_controller: bool = False,
              auto_bind: bool = False) -> tuple[PartialJointSpec, ...]:
        plan = plan_create_partial_joints(
            self._host.capture_partial_candidates(),
            self._host.resolve_partial_selection(), count=count,
            include_controller=include_controller, auto_bind=auto_bind)
        self._host.preflight_partial_scene(
            include_controller=include_controller, multi=count > 1,
            auto_bind=auto_bind)
        for spec in plan.specs:
            for name in spec.names:
                if self._host.find_name_collisions(name):
                    raise ValueError("Partial Joints 节点名称冲突：" + name)
        with self._host.transaction("创建 Partial Joints"):
            for spec in plan.specs:
                self._host.create_partial_joint(spec)
            for spec in plan.specs:
                single, multi = self._host.capture_partial_presence(spec.joint)
                if (single if spec.count == 1 else multi) is not True:
                    raise RuntimeError("Partial Joints 写后复检失败：" + spec.joint)
        return plan.specs


class DeletePartialJoints:
    def __init__(self, host: PartialJointsHost):
        self._host = host

    def apply(self) -> tuple[PartialDeleteSpec, ...]:
        plan = plan_delete_partial_joints(
            self._host.capture_partial_candidates(),
            self._host.resolve_partial_selection())
        with self._host.transaction("删除 Partial Joints"):
            for spec in plan.specs:
                self._host.delete_partial_joint(spec)
            if plan.delete_all:
                self._host.remove_empty_partial_system()
            for spec in plan.specs:
                if any(self._host.capture_partial_presence(spec.joint)):
                    raise RuntimeError("Partial Joints 删除复检失败：" + spec.joint)
        return plan.specs
