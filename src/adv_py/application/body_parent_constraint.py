"""Host contract for one ADV Body parent constraint operation."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.body_parent_constraint import (
    BodyParentConstraintInput, BodyParentConstraintPlan,
    BodyParentConstraintState, audit_body_parent_constraint,
    parse_body_parent_constraint_flags, plan_body_parent_constraint,
)


class BodyParentConstraintHost(Protocol):
    def capture_parent_constraint_input(
        self, driver: str, driven: str, maintain_offset: bool,
    ) -> BodyParentConstraintInput: ...

    def preflight_parent_constraint(
        self, plan: BodyParentConstraintPlan,
    ) -> None: ...

    def create_parent_constraint(
        self, plan: BodyParentConstraintPlan,
    ) -> None: ...

    def capture_parent_constraint_state(
        self, plan: BodyParentConstraintPlan,
    ) -> BodyParentConstraintState: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class BuildBodyParentConstraint:
    def __init__(self, host: BodyParentConstraintHost) -> None:
        self._host = host

    def plan(self, driver: str, driven: str,
             flags: tuple[str, ...] = ()) -> BodyParentConstraintPlan:
        maintain_offset, skip_scale, include_pick, use_decompose, force_mm = (
            parse_body_parent_constraint_flags(flags))
        source = self._host.capture_parent_constraint_input(
            driver, driven, maintain_offset)
        if source.driver != driver or source.driven != driven:
            raise ValueError("宿主回报的约束目标与请求不符")
        source = replace(
            source, maintain_offset=maintain_offset, skip_scale=skip_scale,
            include_pick_matrix=include_pick,
            use_decompose_matrix=use_decompose,
            force_mult_matrix=force_mm)
        plan = plan_body_parent_constraint(source)
        self._host.preflight_parent_constraint(plan)
        return plan

    def apply(self, driver: str, driven: str,
              flags: tuple[str, ...] = ()) -> BodyParentConstraintPlan:
        plan = self.plan(driver, driven, flags)
        with self._host.transaction("创建 Body Parent Constraint"):
            self._host.create_parent_constraint(plan)
            issues = audit_body_parent_constraint(
                plan, self._host.capture_parent_constraint_state(plan))
            if issues:
                raise RuntimeError("Body Parent Constraint 写后状态不符："
                                   + "；".join(issues))
        return plan
