from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_hierarchy import (
    FitHierarchyIssue,
    FitHierarchyPolicy,
    FitHierarchySnapshot,
    FitHierarchyValidationError,
    audit_fit_hierarchy,
)


class FitHierarchyReader(Protocol):
    def capture_fit_hierarchy(self, container_name: str) -> FitHierarchySnapshot: ...


@dataclass(frozen=True, slots=True)
class FitHierarchyAudit:
    snapshot: FitHierarchySnapshot
    issues: tuple[FitHierarchyIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues

    def require_valid(self) -> FitHierarchySnapshot:
        if self.issues:
            details = "；".join(issue.message for issue in self.issues)
            raise FitHierarchyValidationError(
                f"FitSkeleton 构建前校验失败：{details}"
            )
        return self.snapshot


class InspectFitHierarchy:
    """Capture a complete hierarchy once, then run portable preflight rules."""

    def __init__(self, host: FitHierarchyReader) -> None:
        self._host = host

    def execute(
        self,
        container_name: str = "FitSkeleton",
        policy: FitHierarchyPolicy | None = None,
    ) -> FitHierarchyAudit:
        if not container_name.strip():
            raise FitHierarchyValidationError("FitSkeleton 容器名称不能为空")
        snapshot = self._host.capture_fit_hierarchy(container_name)
        return FitHierarchyAudit(
            snapshot=snapshot,
            issues=audit_fit_hierarchy(snapshot, policy),
        )
