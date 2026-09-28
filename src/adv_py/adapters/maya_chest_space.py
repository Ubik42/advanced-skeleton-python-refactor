"""Chest-space follow for fixed and variable Body spine mechanisms."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.body_parent_constraint import (
    audit_body_parent_constraint, plan_body_parent_constraint,
)
from adv_py.core.fit_settings import FitSkeletonValidationError


def _matrix_plan(host, driver: str, driven: str):
    source = host.capture_parent_constraint_input(driver, driven, False)
    return plan_body_parent_constraint(replace(
        source, use_offset_parent_matrix=True, skip_scale=True,
        include_pick_matrix=True))


def create(host, driver: str, driven: str, name: str,
           use_offset_parent_matrix: bool) -> None:
    if not use_offset_parent_matrix:
        nodes = host._cmds.parentConstraint(
            driver, driven, maintainOffset=False, name=name)
        if len(nodes) != 1:
            raise FitSkeletonValidationError("Chest Space 父约束创建失败")
        return
    plan = _matrix_plan(host, driver, driven)
    host.preflight_parent_constraint(plan)
    host.create_parent_constraint(plan)
    audit(host, driver, driven, name, True)


def audit(host, driver: str, driven: str, name: str,
          use_offset_parent_matrix: bool) -> None:
    if not use_offset_parent_matrix:
        actual = host._cmds.parentConstraint(name, query=True,
                                             targetList=True) or []
        targets = tuple(host._resolve_connected_node(node) for node in actual)
        if targets != (driver,):
            raise FitSkeletonValidationError("Chest Space 父约束来源改变")
        return
    plan = _matrix_plan(host, driver, driven)
    issues = audit_body_parent_constraint(
        plan, host.capture_parent_constraint_state(plan))
    if issues:
        raise FitSkeletonValidationError(
            "Chest Space OPM 跟随图不符：" + "；".join(issues))
