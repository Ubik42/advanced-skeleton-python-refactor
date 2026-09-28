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


PRUNE_THRESHOLD = 0.01


@dataclass(frozen=True, slots=True)
class SkinWeightState:
    skin: str
    shape: str
    vertex_count: int
    influence_count: int
    weak_count: int
    locked_weak_count: int


@dataclass(frozen=True, slots=True)
class PruneSkinWeightsPlan:
    before: tuple[SkinWeightState, ...]
    threshold: float = PRUNE_THRESHOLD


def plan_prune_skin_weights(
        before: tuple[SkinWeightState, ...]) -> PruneSkinWeightsPlan:
    if not before:
        raise ValueError("当前角色 Geometry 下没有蒙皮网格")
    if len({(item.skin, item.shape) for item in before}) != len(before):
        raise ValueError("重复的 Skin 网格")
    for item in before:
        if (item.vertex_count < 1 or item.influence_count < 1
                or item.weak_count < 0
                or item.locked_weak_count < 0
                or item.locked_weak_count > item.weak_count):
            raise ValueError("Skin 权重计数无效：" + item.shape)
        if item.locked_weak_count:
            raise ValueError("低权重影响关节被锁定，无法修剪：" + item.shape)
    return PruneSkinWeightsPlan(before)


def audit_pruned_skin_weights(
        plan: PruneSkinWeightsPlan,
        after: tuple[SkinWeightState, ...]) -> tuple[str, ...]:
    if tuple((item.skin, item.shape, item.vertex_count,
              item.influence_count) for item in after) != tuple(
            (item.skin, item.shape, item.vertex_count,
             item.influence_count) for item in plan.before):
        return ("Skin 网格或拓扑在修剪期间改变",)
    for item in after:
        if item.weak_count:
            return ("仍有低于 0.01 的非零 Skin 权重：" + item.shape,)
    return ()
