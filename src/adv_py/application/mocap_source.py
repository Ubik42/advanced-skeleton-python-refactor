from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.mocap_source import (
    MocapSourceIssue,
    MocapSourceSnapshot,
    MocapSourceSummary,
    MocapSourceValidationError,
    audit_mocap_source,
    summarize_mocap_source,
)


class MocapSourceReader(Protocol):
    def capture_mocap_source(self, root_name: str) -> MocapSourceSnapshot: ...


@dataclass(frozen=True, slots=True)
class MocapSourceInspection:
    snapshot: MocapSourceSnapshot
    issues: tuple[MocapSourceIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues

    def require_valid(self) -> MocapSourceSummary:
        if self.issues:
            raise MocapSourceValidationError(
                "MoCap 来源检查失败："
                + "；".join(issue.message for issue in self.issues)
            )
        return summarize_mocap_source(self.snapshot)


class InspectMocapSource:
    """Capture one explicit skeleton root and audit it without scene mutation."""

    def __init__(self, host: MocapSourceReader) -> None:
        self._host = host

    def execute(self, root_name: str) -> MocapSourceInspection:
        if not isinstance(root_name, str) or not root_name.strip():
            raise MocapSourceValidationError("MoCap 根关节名称不能为空")
        snapshot = self._host.capture_mocap_source(root_name)
        return MocapSourceInspection(snapshot, audit_mocap_source(snapshot))
