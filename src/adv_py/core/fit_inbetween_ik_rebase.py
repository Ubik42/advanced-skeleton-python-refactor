"""Rebase rig references after Inbetween joints enter an IK DAG chain."""
from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from enum import Enum
from typing import TypeVar

from .body_limb_mechanisms import BodyLimbMechanismPlan, BodyLimbMechanismRole
from .body_spine import BodySpinePlan
from .fit_inbetween_ik_solver import InbetweenIkSolverPlan


T = TypeVar("T")


def rebase_inbetween_ik_reference(
    value: T,
    solvers: tuple[InbetweenIkSolverPlan, ...],
) -> T:
    """Rewrite DAG paths and plugs in an immutable rig plan.

    Longest-prefix matching matters when both Elbow and Wrist move: a Wrist
    path must use its own final path, not the intermediate Elbow rewrite.
    Enum values and plain labels are left alone.  This is intended for plans,
    not live scene snapshots captured before the topology change.
    """
    rewrites = tuple(sorted(
        (pair for solver in solvers for pair in solver.path_rewrites),
        key=lambda pair: len(pair[0]), reverse=True))
    old_paths = [before for before, _ in rewrites]
    if len(set(old_paths)) != len(old_paths):
        raise ValueError("Inbetween IK 路径改写来源重复")

    def visit(item):
        if isinstance(item, Enum):
            return item
        if isinstance(item, str):
            for before, after in rewrites:
                if (item == before or item.startswith(before + "|")
                        or item.startswith(before + ".")):
                    return after + item[len(before):]
            return item
        if is_dataclass(item) and not isinstance(item, type):
            changes = {
                field.name: visit(getattr(item, field.name))
                for field in fields(item) if field.init
            }
            return replace(item, **changes)
        if isinstance(item, tuple):
            return tuple(visit(part) for part in item)
        if isinstance(item, list):
            return [visit(part) for part in item]
        if isinstance(item, dict):
            return {visit(key): visit(part) for key, part in item.items()}
        return item

    return visit(value)


def rebase_inbetween_ik_mechanisms(
    plan: BodyLimbMechanismPlan,
    solvers: tuple[InbetweenIkSolverPlan, ...],
) -> BodyLimbMechanismPlan:
    """Set each moved mechanism joint's actual new Part parent."""
    rebased = rebase_inbetween_ik_reference(plan, solvers)
    moved = {new for solver in solvers for _, new in solver.path_rewrites}
    joints = tuple(
        replace(spec, parent_path=spec.path.rsplit("|", 1)[0])
        if spec.role is BodyLimbMechanismRole.IK and spec.path in moved
        else spec
        for spec in rebased.joints
    )
    return replace(rebased, joints=joints)


def rebase_inbetween_spine_mechanisms(
    plan: BodySpinePlan,
    solvers: tuple[InbetweenIkSolverPlan, ...],
) -> BodySpinePlan:
    """Update the fixed Spine mechanism paths and their changed parents."""
    rebased = rebase_inbetween_ik_reference(plan, solvers)
    moved = {new for solver in solvers for _, new in solver.path_rewrites}
    joints = tuple(
        replace(spec, parent_path=spec.path.rsplit("|", 1)[0])
        if spec.role is BodyLimbMechanismRole.IK and spec.path in moved
        else spec
        for spec in rebased.joints
    )
    return replace(rebased, joints=joints)
