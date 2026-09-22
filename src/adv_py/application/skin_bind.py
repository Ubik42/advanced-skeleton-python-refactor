from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.skin_bind import (
    SkinBindInputState,
    SkinBindIssue,
    SkinBindPlan,
    SkinBindSnapshot,
    audit_skin_bind_input,
    audit_skin_bind_result,
    plan_skin_bind,
)


class SkinBindHost(Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_skin_bind_input(self, plan: SkinBindPlan) -> SkinBindInputState: ...
    def create_skin_bind(self, plan: SkinBindPlan) -> None: ...
    def capture_skin_bind(self, plan: SkinBindPlan) -> SkinBindSnapshot: ...


@dataclass(frozen=True, slots=True)
class SkinBindBuildPlan:
    bind: SkinBindPlan
    input_state: SkinBindInputState
    input_issues: tuple[SkinBindIssue, ...]
    name_collisions: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.input_issues and not self.name_collisions

    @property
    def blockers(self) -> tuple[str, ...]:
        values = [
            issue.message + (f"：{issue.subject}" if issue.subject else "")
            for issue in self.input_issues
        ]
        if self.name_collisions:
            values.append(
                "场景中存在 Skin Bind 同名节点："
                + "、".join(self.name_collisions)
            )
        return tuple(values)


@dataclass(frozen=True, slots=True)
class SkinBindBuildResult:
    plan: SkinBindBuildPlan
    snapshot: SkinBindSnapshot


class BindSkin:
    """Bind one explicit mesh to explicit joints without selection-driven discovery."""

    def __init__(self, host: SkinBindHost) -> None:
        self._host = host

    def plan(
        self,
        mesh_path: str,
        influence_paths: tuple[str, ...],
        *,
        skin_name: str = "AdvPy_BodySkin",
        maximum_influences: int = 4,
        maintain_maximum_influences: bool = True,
    ) -> SkinBindBuildPlan:
        bind = plan_skin_bind(
            mesh_path,
            influence_paths,
            skin_name=skin_name,
            maximum_influences=maximum_influences,
            maintain_maximum_influences=maintain_maximum_influences,
        )
        state = self._host.capture_skin_bind_input(bind)
        return SkinBindBuildPlan(
            bind,
            state,
            audit_skin_bind_input(bind, state),
            self._host.find_name_collisions(bind.skin_name),
        )

    def apply(
        self,
        mesh_path: str,
        influence_paths: tuple[str, ...],
        *,
        skin_name: str = "AdvPy_BodySkin",
        maximum_influences: int = 4,
        maintain_maximum_influences: bool = True,
    ) -> SkinBindBuildResult:
        plan = self.plan(
            mesh_path,
            influence_paths,
            skin_name=skin_name,
            maximum_influences=maximum_influences,
            maintain_maximum_influences=maintain_maximum_influences,
        )
        if not plan.ready:
            raise FitSkeletonValidationError(
                "Skin Bind 预检失败，场景未修改："
                + "；".join(plan.blockers)
            )
        with self._host.transaction("绑定显式网格到显式关节"):
            current = self._host.capture_skin_bind_input(plan.bind)
            if current != plan.input_state or audit_skin_bind_input(
                plan.bind,
                current,
            ):
                raise FitSkeletonValidationError("Skin Bind 输入在执行前发生变化")
            self._host.create_skin_bind(plan.bind)
            snapshot = self._host.capture_skin_bind(plan.bind)
            issues = audit_skin_bind_result(plan.bind, snapshot)
            if issues:
                raise RuntimeError(
                    "Skin Bind 构建后复检失败："
                    + "；".join(issue.message for issue in issues)
                )
        return SkinBindBuildResult(plan, snapshot)
