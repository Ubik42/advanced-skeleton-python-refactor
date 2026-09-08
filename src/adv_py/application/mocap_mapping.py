from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from adv_py.core.body_skeleton import (
    BodySkeletonProvenance,
    BodySkeletonSnapshot,
    oriented_body_provenance,
)
from adv_py.core.mocap_mapping import (
    MocapBodyMappingPlan,
    MocapJointMapping,
    MocapMappingIssue,
    MocapMappingValidationError,
    audit_mocap_body_mapping,
    plan_mocap_body_mapping,
)
from adv_py.core.mocap_source import MocapSourceSnapshot


class MocapBodyMappingReader(Protocol):
    def capture_mocap_source(self, root_name: str) -> MocapSourceSnapshot: ...
    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot: ...


@dataclass(frozen=True, slots=True)
class MocapBodyMappingInspection:
    source: MocapSourceSnapshot
    body: BodySkeletonSnapshot
    mappings: tuple[MocapJointMapping, ...]
    expected_body_provenance: BodySkeletonProvenance
    issues: tuple[MocapMappingIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues

    def require_valid(self) -> MocapBodyMappingPlan:
        if self.issues:
            raise MocapMappingValidationError(
                "MoCap→Body 映射失败："
                + "；".join(issue.message for issue in self.issues)
            )
        return plan_mocap_body_mapping(
            self.source,
            self.body,
            self.mappings,
            self.expected_body_provenance,
        )


class InspectMocapBodyMapping:
    """Resolve an explicit mapping against one source and one owned Body."""

    def __init__(self, host: MocapBodyMappingReader) -> None:
        self._host = host

    def execute(
        self,
        source_root_name: str,
        mappings: Sequence[MocapJointMapping],
        *,
        body_root_name: str = "Root_M",
        source_container: str = "|FitSkeleton",
        expected_body_joint_count: int = 30,
    ) -> MocapBodyMappingInspection:
        if not isinstance(source_root_name, str) or not source_root_name.strip():
            raise MocapMappingValidationError("MoCap 根关节名称不能为空")
        if not isinstance(body_root_name, str) or not body_root_name.strip():
            raise MocapMappingValidationError("Body 根关节名称不能为空")
        resolved_mappings = tuple(mappings)
        if any(not isinstance(item, MocapJointMapping) for item in resolved_mappings):
            raise MocapMappingValidationError("MoCap→Body 映射项类型无效")
        expected = oriented_body_provenance(
            source_container,
            expected_body_joint_count,
        )
        source = self._host.capture_mocap_source(source_root_name)
        body = self._host.capture_body_skeleton(body_root_name)
        return MocapBodyMappingInspection(
            source=source,
            body=body,
            mappings=resolved_mappings,
            expected_body_provenance=expected,
            issues=audit_mocap_body_mapping(
                source,
                body,
                resolved_mappings,
                expected,
            ),
        )
