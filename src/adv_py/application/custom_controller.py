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
    influenced_meshes: tuple[str, ...]
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
                    or set(state.influenced_meshes) != {plan.region.mesh}
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
                    or (plan.kind is CustomControlKind.SOFT_MOD
                        and state.weighted_vertex_count != sum(
                            item.weight > 0.0 for item in plan.region.weights))
                    or (plan.kind in (CustomControlKind.CLUSTER,
                                     CustomControlKind.SKIN)
                        and state.weighted_vertex_count < 1)):
                raise RuntimeError("自定义控制器写后复检失败")
        return CustomControllerBuildResult(plan, state)


@dataclass(frozen=True, slots=True)
class SoftModExtensionPlan:
    kind: CustomControlKind
    control: str
    deformer: str
    joint: str | None
    mesh: str
    expected_meshes: tuple[str, ...]


class SoftModExtensionHost(Protocol):
    def capture_custom_control(self, control: str) -> CustomControllerState: ...
    def resolve_custom_mesh(self, mesh: str) -> str: ...
    def preflight_custom_extension(self, kind: CustomControlKind,
                                   deformer: str, joint: str | None,
                                   mesh: str) -> None: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def add_custom_influenced_mesh(self, kind: CustomControlKind,
                                   deformer: str, joint: str | None,
                                   mesh: str) -> None: ...


class ExtendSoftModController:
    """Add one mesh to an existing SoftMod or Cluster control."""

    def __init__(self, host: SoftModExtensionHost):
        self._host = host

    def plan(self, control: str, mesh: str) -> SoftModExtensionPlan:
        if not isinstance(control, str) or not control.strip():
            raise ValueError("自定义控制器路径不能为空")
        if not isinstance(mesh, str) or not mesh.strip():
            raise ValueError("新增受影响网格路径不能为空")
        mesh = self._host.resolve_custom_mesh(mesh)
        state = self._host.capture_custom_control(control)
        if not state.deformer or (state.kind is CustomControlKind.SKIN
                                 and not state.joint):
            raise ValueError("所选节点不是完整的自定义控制器")
        if len(state.influenced_meshes) != len(set(state.influenced_meshes)):
            raise ValueError("变形器影响集合包含重复网格")
        if mesh in state.influenced_meshes:
            raise ValueError("网格已经属于变形器影响集合")
        self._host.preflight_custom_extension(
            state.kind, state.deformer, state.joint, mesh)
        return SoftModExtensionPlan(
            state.kind, control, state.deformer, state.joint, mesh,
            state.influenced_meshes + (mesh,))

    def apply(self, control: str, mesh: str) -> CustomControllerState:
        plan = self.plan(control, mesh)
        with self._host.transaction("添加自定义控制器受影响对象"):
            self._host.add_custom_influenced_mesh(
                plan.kind, plan.deformer, plan.joint, plan.mesh)
            state = self._host.capture_custom_control(plan.control)
            if (state.kind is not plan.kind
                    or state.deformer != plan.deformer
                    or len(state.influenced_meshes) != len(plan.expected_meshes)
                    or set(state.influenced_meshes) != set(plan.expected_meshes)):
                raise RuntimeError("自定义控制器影响对象写后复检失败")
        return state
