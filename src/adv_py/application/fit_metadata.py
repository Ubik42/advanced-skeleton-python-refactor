from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from adv_py.core.fit_metadata import (
    FitJointIssue,
    FitJointMetadata,
    FitJointValidationError,
    audit_fit_joint,
)


class FitJointMetadataHost(Protocol):
    def resolve_joints(self, names: Sequence[str]) -> tuple[str, ...]: ...

    def read_fit_joint_metadata(self, joint: str) -> FitJointMetadata: ...


@dataclass(frozen=True, slots=True)
class FitJointAudit:
    joints: tuple[FitJointMetadata, ...]
    issues: tuple[FitJointIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


class InspectFitJoints:
    """Read all requested joints first, then audit portable relationships."""

    def __init__(self, host: FitJointMetadataHost) -> None:
        self._host = host

    def execute(self, joints: Sequence[str]) -> FitJointAudit:
        names = tuple(joints)
        if not names:
            raise FitJointValidationError("至少需要一个 Fit joint")
        if any(not name.strip() for name in names):
            raise FitJointValidationError("Fit joint 名称不能为空")
        if len(names) != len(set(names)):
            raise FitJointValidationError("Fit joint 列表不能包含重复项")

        resolved = self._host.resolve_joints(names)
        metadata = tuple(
            self._host.read_fit_joint_metadata(joint) for joint in resolved
        )
        issues = tuple(
            issue for item in metadata for issue in audit_fit_joint(item)
        )
        return FitJointAudit(joints=metadata, issues=issues)
