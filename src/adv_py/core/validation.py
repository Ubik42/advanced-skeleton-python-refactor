from __future__ import annotations

from .model import RigPlan


class PlanValidationError(ValueError):
    pass


def validate_plan(plan: RigPlan) -> None:
    """Reject invalid references and parent cycles before a host transaction starts."""

    if not plan.name.strip():
        raise PlanValidationError("RigPlan.name 不能为空")

    keys = [node.key for node in plan.nodes]
    names = [node.name for node in plan.nodes]
    if len(keys) != len(set(keys)):
        raise PlanValidationError("节点 key 必须唯一")
    if len(names) != len(set(names)):
        raise PlanValidationError("节点 name 必须唯一")

    known = set(keys)
    parent_by_key = {node.key: node.parent for node in plan.nodes}
    for node in plan.nodes:
        if not node.key.strip() or not node.name.strip():
            raise PlanValidationError("节点 key 和 name 不能为空")
        if node.parent is not None and node.parent not in known:
            raise PlanValidationError(f"节点 {node.key!r} 引用了不存在的父节点 {node.parent!r}")

    for key in keys:
        visited: set[str] = set()
        current: str | None = key
        while current is not None:
            if current in visited:
                raise PlanValidationError(f"节点层级存在循环：{key!r}")
            visited.add(current)
            current = parent_by_key[current]

    for constraint in plan.constraints:
        if not constraint.sources:
            raise PlanValidationError("约束至少需要一个 source")
        missing = [key for key in (*constraint.sources, constraint.target) if key not in known]
        if missing:
            raise PlanValidationError(f"约束引用了不存在的节点：{', '.join(missing)}")
        if constraint.target in constraint.sources:
            raise PlanValidationError("约束 target 不能同时作为 source")

