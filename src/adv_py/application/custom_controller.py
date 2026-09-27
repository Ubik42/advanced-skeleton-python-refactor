"""Create Body or Face custom controls from a painted SoftMod region."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.custom_controller import (
    CustomControlKind, CustomControllerPlan, DeformJointCandidate,
    SoftModRegion, plan_custom_controller,
)


@dataclass(frozen=True, slots=True)
class CustomControllerState:
    kind: CustomControlKind
    offset: str
    control: str
    base_control: str | None
    parent_joint: str
    mesh: str
    joint: str | None
    deformer: str | None
    weighted_vertex_count: int


class CustomControllerHost(Protocol):
    def capture_softmod_region(self, deformer: str) -> SoftModRegion: ...
    def deform_joint_candidates(self, mesh: str) -> tuple[DeformJointCandidate, ...]: ...
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def preflight_custom_controller(self, plan: CustomControllerPlan) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def create_custom_controller(self, plan: CustomControllerPlan) -> None: ...
    def capture_custom_controller(self, plan: CustomControllerPlan) -> CustomControllerState: ...


@dataclass(frozen=True, slots=True)
class CustomControllerBuildResult:
    plan: CustomControllerPlan
    state: CustomControllerState


class BuildCustomController:
    def __init__(self, host: CustomControllerHost):
        self._host = host

    def plan(self, deformer: str, kind: CustomControlKind,
             base_name: str, *, parent_joint: str | None = None
             ) -> CustomControllerPlan:
        region = self._host.capture_softmod_region(deformer)
        joints = self._host.deform_joint_candidates(region.mesh)
        plan = plan_custom_controller(kind, region, joints, base_name,
                                      parent_joint=parent_joint)
        for name in plan.created_names:
            if self._host.find_name_collisions(name):
                raise ValueError("自定义控制节点名称已占用：" + name)
        self._host.preflight_custom_controller(plan)
        return plan

    def apply(self, deformer: str, kind: CustomControlKind,
              base_name: str, *, parent_joint: str | None = None
              ) -> CustomControllerBuildResult:
        plan = self.plan(deformer, kind, base_name,
                         parent_joint=parent_joint)
        with self._host.transaction("创建自定义控制器"):
            self._host.create_custom_controller(plan)
            state = self._host.capture_custom_controller(plan)
            if (state.kind is not plan.kind or state.parent_joint != plan.parent_joint
                    or state.mesh != plan.region.mesh
                    or state.offset.rsplit("|", 1)[-1] != plan.offset_name
                    or state.control.rsplit("|", 1)[-1] != plan.control_name
                    or (state.base_control is None) !=
                       (plan.base_control_name is None)
                    or (plan.base_control_name is not None
                        and state.base_control.rsplit("|", 1)[-1]
                        != plan.base_control_name)
                    or (state.joint is None) != (plan.joint_name is None)
                    or (plan.joint_name is not None
                        and state.joint.rsplit("|", 1)[-1] != plan.joint_name)
                    or (plan.deformer_name is not None
                        and (state.deformer is None or
                             state.deformer.rsplit("|", 1)[-1]
                             != plan.deformer_name))
                    or state.weighted_vertex_count != sum(
                        item.weight > 0.0 for item in plan.region.weights)):
                raise RuntimeError("自定义控制器写后复检失败")
        return CustomControllerBuildResult(plan, state)
