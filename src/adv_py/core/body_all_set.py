"""Plan the original AllSet from nodes created during Body construction."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BodyAllSetNode:
    path: str
    node_type: str
    referenced: bool = False


@dataclass(frozen=True, slots=True)
class BodyAllSetPlan:
    members: tuple[str, ...]
    set_name: str = "AllSet"


def plan_body_all_set(
    before: tuple[BodyAllSetNode, ...],
    after: tuple[BodyAllSetNode, ...],
    fit_container: str,
) -> BodyAllSetPlan:
    fit_name = fit_container.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    if not fit_name or "." in fit_name:
        raise ValueError("AllSet 缺少 Fit 容器")
    for label, nodes in (("构建前", before), ("构建后", after)):
        if len({node.path for node in nodes}) != len(nodes):
            raise ValueError("AllSet " + label + "节点清单包含重复路径")
        if any(not node.path or not node.node_type for node in nodes):
            raise ValueError("AllSet " + label + "节点清单无效")
    old = {node.path for node in before}
    fit_root = "|Group|" + fit_name
    geometry = "|Group|Geometry"
    excluded = {"Sets", "AllSet", geometry}
    members = []
    for node in after:
        path = node.path
        if (node.referenced or node.node_type in ("ikSolver", "ikSystem")
                or path in excluded
                or path == fit_root or path.startswith(fit_root + "|")
                or path.startswith(geometry + "|")):
            continue
        # Group is created by the same outer build even when this use case
        # enters after its hierarchy has been prepared by the caller.
        if path not in old or path == "|Group" or path.startswith("|Group|"):
            members.append(path)
    if not members:
        raise ValueError("AllSet 没有可登记的角色节点")
    return BodyAllSetPlan(tuple(sorted(members)))
