from __future__ import annotations

from typing import Protocol, Sequence

from adv_py.core.mocap_bake import (
    MocapBodyBakePlan, MocapBodySample, plan_mocap_body_bake,
    validate_mocap_samples, verify_mocap_bake_samples,
)
from adv_py.core.mocap_connection import audit_mocap_connection, plan_mocap_body_connection
from adv_py.core.mocap_mapping import MocapJointMapping, MocapMappingValidationError
from .mocap_connection import MocapBodyConnectionHost
from .mocap_mapping import InspectMocapBodyMapping


class MocapBodyBakeHost(MocapBodyConnectionHost, Protocol):
    def preflight_mocap_bake(self, plan: MocapBodyBakePlan) -> None: ...
    def sample_mocap_body(self, plan: MocapBodyBakePlan) -> tuple[MocapBodySample, ...]: ...
    def write_mocap_keys(self, plan: MocapBodyBakePlan, samples: tuple[MocapBodySample, ...]) -> None: ...
    def verify_mocap_keys(self, plan: MocapBodyBakePlan, samples: tuple[MocapBodySample, ...]) -> None: ...


class BakeMocapBody:
    """Consume an existing explicit connection; preserve its established offsets."""

    def __init__(self, host: MocapBodyBakeHost) -> None:
        self._host = host

    def plan(
        self, source_root_name: str, mappings: Sequence[MocapJointMapping], *,
        start_frame: int, end_frame: int, sample_by: int = 1,
        body_root_name: str = "Root_M", source_container: str = "|FitSkeleton",
        expected_body_joint_count: int = 30,
    ) -> MocapBodyBakePlan:
        mapping = InspectMocapBodyMapping(self._host).execute(
            source_root_name, mappings, body_root_name=body_root_name,
            source_container=source_container, expected_body_joint_count=expected_body_joint_count,
        ).require_valid()
        plan = plan_mocap_body_bake(
            plan_mocap_body_connection(mapping), start_frame, end_frame, sample_by,
        )
        self._preflight(plan)
        return plan

    def _preflight(self, plan: MocapBodyBakePlan) -> None:
        issues = audit_mocap_connection(
            plan.connection, self._host.capture_mocap_connection(plan.connection),
        )
        if issues:
            raise MocapMappingValidationError("MoCap bake 需要完整临时驱动：" + "；".join(i.message for i in issues))
        self._host.preflight_mocap_bake(plan)

    def execute(
        self, source_root_name: str, mappings: Sequence[MocapJointMapping], **options,
    ) -> tuple[MocapBodySample, ...]:
        plan = self.plan(source_root_name, mappings, **options)
        samples = self._host.sample_mocap_body(plan)
        validate_mocap_samples(plan, samples)
        # Sampling may evaluate user callbacks; repeat the complete preflight before mutation.
        if self.plan(source_root_name, mappings, **options) != plan:
            raise MocapMappingValidationError("MoCap bake 计划在采样期间发生变化")
        with self._host.transaction("AdvPy Bake MoCap Body"):
            self._host.delete_mocap_constraints(plan.connection)
            if self._host.find_mocap_name_collisions(plan.connection):
                raise MocapMappingValidationError("MoCap bake 临时约束删除不完整")
            self._host.write_mocap_keys(plan, samples)
            self._host.verify_mocap_keys(plan, samples)
            verify_mocap_bake_samples(plan, samples, self._host.sample_mocap_body(plan))
        return samples
