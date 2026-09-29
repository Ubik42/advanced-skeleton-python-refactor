"""Plan AdvancedSkeleton Fit chain resampling without Maya dependencies."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_hierarchy import FitHierarchySnapshot


@dataclass(frozen=True, slots=True)
class FitResamplePlan:
    container: str
    start: str
    end: str
    old_chain: tuple[str, ...]
    new_names: tuple[str, ...]
    joint_count: int


def plan_fit_resample(hierarchy: FitHierarchySnapshot, start: str,
                      end: str, joint_count: int) -> FitResamplePlan:
    """Resolve the exact chain and reserve intermediate names before mutation."""
    if type(joint_count) is not int or not 2 <= joint_count <= 99:
        raise ValueError("重采样关节总数须为 2..99")
    nodes = {node.path: node for node in hierarchy.joints}
    def resolve(value: str) -> str:
        matches = [path for path, node in nodes.items()
                   if path == value or node.short_name == value]
        if len(matches) != 1:
            raise ValueError("Fit 重采样关节名称缺失或不唯一：" + value)
        return matches[0]
    start_path, end_path = resolve(start), resolve(end)
    if start_path == end_path:
        raise ValueError("重采样起点与终点不能相同")
    chain = [end_path]
    while chain[-1] != start_path:
        parent = nodes[chain[-1]].dag_parent
        if parent not in nodes:
            raise ValueError("重采样终点必须是起点的后代")
        chain.append(parent)
    chain.reverse()
    for path in chain[1:-1]:
        children = {node.path for node in hierarchy.joints
                    if node.dag_parent == path}
        if children != {chain[chain.index(path) + 1]}:
            raise ValueError("重采样链中间关节存在分支：" + path)
    short = nodes[start_path].short_name
    first = nodes[chain[1]].short_name
    base = ("Spine" if short == "Root" and
            (first.startswith("Spine") or first == "Chest") else short)
    old_names = {node.short_name for node in hierarchy.joints}
    reusable = {nodes[path].short_name for path in chain[1:-1]}
    reserved = old_names - reusable
    new_names = []
    for _ in range(joint_count - 2):
        for index in range(1 if base == "Spine" else 0, 100):
            name = base + (str(index) if index else "")
            if name not in reserved and name not in new_names:
                new_names.append(name)
                break
        else:
            raise ValueError("重采样关节名称序号已用尽：" + base)
    return FitResamplePlan(hierarchy.container, start_path, end_path,
                           tuple(chain), tuple(new_names), joint_count)
