"""Plans and readback for the original Optimize skin influence action."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkinInfluenceState:
    skin: str
    influence_count: int
    unused_count: int


@dataclass(frozen=True, slots=True)
class SkinOptimizePlan:
    before: tuple[SkinInfluenceState, ...]


def plan_remove_unused_influences(
        before: tuple[SkinInfluenceState, ...]) -> SkinOptimizePlan:
    if not before:
        raise ValueError("当前角色 Geometry 下没有蒙皮网格")
    if len({item.skin for item in before}) != len(before):
        raise ValueError("重复的 Skin 节点")
    if any(item.unused_count < 0 or item.influence_count < item.unused_count
           for item in before):
        raise ValueError("Skin 影响关节计数无效")
    return SkinOptimizePlan(before)


def audit_removed_influences(
        plan: SkinOptimizePlan,
        after: tuple[SkinInfluenceState, ...]) -> tuple[str, ...]:
    if tuple(item.skin for item in after) != tuple(
            item.skin for item in plan.before):
        return ("Skin 集合在清理期间改变",)
    for old, new in zip(plan.before, after):
        if new.unused_count or new.influence_count != (
                old.influence_count - old.unused_count):
            return (f"未能核对无效影响关节的清理结果：{old.skin}",)
    return ()
