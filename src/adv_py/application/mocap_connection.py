from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, Sequence

from adv_py.core.mocap_connection import (
    MocapBodyConnectionPlan,
    MocapBodyConnectionSnapshot,
    MocapTargetInputState,
    MocapTargetPose,
    audit_mocap_connection,
    audit_mocap_connection_input,
    mocap_target_poses_match,
    plan_mocap_body_connection,
)
from adv_py.core.mocap_mapping import MocapJointMapping, MocapMappingValidationError

from .mocap_mapping import InspectMocapBodyMapping, MocapBodyMappingReader


class MocapBodyConnectionHost(MocapBodyMappingReader, Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def find_mocap_name_collisions(self, plan: MocapBodyConnectionPlan) -> tuple[str, ...]: ...
    def capture_mocap_target_inputs(self, plan: MocapBodyConnectionPlan) -> tuple[MocapTargetInputState, ...]: ...
    def capture_mocap_target_poses(self, plan: MocapBodyConnectionPlan) -> tuple[MocapTargetPose, ...]: ...
    def create_mocap_constraints(self, plan: MocapBodyConnectionPlan) -> None: ...
    def capture_mocap_connection(self, plan: MocapBodyConnectionPlan) -> MocapBodyConnectionSnapshot: ...
    def delete_mocap_constraints(self, plan: MocapBodyConnectionPlan) -> None: ...


@dataclass(frozen=True, slots=True)
class MocapBodyConnectionResult:
    plan: MocapBodyConnectionPlan
    snapshot: MocapBodyConnectionSnapshot


class ConnectMocapBody:
    def __init__(self, host: MocapBodyConnectionHost) -> None:
        self._host = host

    def execute(
        self,
        source_root_name: str,
        mappings: Sequence[MocapJointMapping],
        *,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        expected_body_joint_count: int = 30,
    ) -> MocapBodyConnectionResult:
        mapping_args = dict(
            body_root_name=body_root_name,
            source_container=source_container,
            expected_body_joint_count=expected_body_joint_count,
        )
        inspector = InspectMocapBodyMapping(self._host)
        inspection = inspector.execute(source_root_name, mappings, **mapping_args)
        plan = plan_mocap_body_connection(inspection.require_valid())
        inputs = self._host.capture_mocap_target_inputs(plan)
        issues = audit_mocap_connection_input(
            plan, self._host.find_mocap_name_collisions(plan), inputs
        )
        if issues:
            raise MocapMappingValidationError(
                "MoCap 临时驱动预检失败：" + "；".join(item.message for item in issues)
            )
        repeated = inspector.execute(source_root_name, mappings, **mapping_args)
        if repeated.source != inspection.source or repeated.body != inspection.body:
            raise MocapMappingValidationError("MoCap 或 Body 在事务前发生变化")
        before_pose = self._host.capture_mocap_target_poses(plan)
        with self._host.transaction("AdvPy Connect MoCap Body"):
            self._host.create_mocap_constraints(plan)
            snapshot = self._host.capture_mocap_connection(plan)
            issues = audit_mocap_connection(plan, snapshot)
            if issues:
                raise MocapMappingValidationError(
                    "MoCap 临时驱动复检失败：" + "；".join(item.message for item in issues)
                )
            if not mocap_target_poses_match(
                before_pose, self._host.capture_mocap_target_poses(plan)
            ):
                raise MocapMappingValidationError("MoCap maintain-offset 未保持 Body 当前姿态")
        return MocapBodyConnectionResult(plan, snapshot)


class DisconnectMocapBody:
    def __init__(self, host: MocapBodyConnectionHost) -> None:
        self._host = host

    def execute(
        self,
        source_root_name: str,
        mappings: Sequence[MocapJointMapping],
        *,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        expected_body_joint_count: int = 30,
    ) -> MocapBodyConnectionPlan:
        mapping = InspectMocapBodyMapping(self._host).execute(
            source_root_name,
            mappings,
            body_root_name=body_root_name,
            source_container=source_container,
            expected_body_joint_count=expected_body_joint_count,
        ).require_valid()
        plan = plan_mocap_body_connection(mapping)
        snapshot = self._host.capture_mocap_connection(plan)
        issues = audit_mocap_connection(plan, snapshot)
        if issues:
            raise MocapMappingValidationError(
                "拒绝断开非本工程完整拥有的 MoCap 临时驱动："
                + "；".join(item.message for item in issues)
            )
        with self._host.transaction("AdvPy Disconnect MoCap Body"):
            self._host.delete_mocap_constraints(plan)
            if self._host.find_mocap_name_collisions(plan):
                raise MocapMappingValidationError("MoCap 临时约束删除不完整")
            inputs = self._host.capture_mocap_target_inputs(plan)
            if audit_mocap_connection_input(plan, (), inputs):
                raise MocapMappingValidationError("MoCap 临时驱动断开后目标输入未释放")
        return plan
