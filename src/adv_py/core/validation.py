from __future__ import annotations

from math import isfinite
import re

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
        if len(node.world_matrix) != 16 or not all(isfinite(value) for value in node.world_matrix):
            raise PlanValidationError(f"节点 {node.key!r} 的世界矩阵必须是 16 个有限数值")
        if any(abs(value) > 1e-8 for value in node.world_matrix[12:15]) or abs(node.world_matrix[15] - 1.0) > 1e-8:
            raise PlanValidationError(f"节点 {node.key!r} 的世界矩阵必须是仿射矩阵")
        if node.kind == "joint" and node.extent <= 0:
            raise PlanValidationError(f"关节 {node.key!r} 的 extent 必须大于 0")
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

    limb_keys = [limb.key for limb in plan.limbs]
    if len(limb_keys) != len(set(limb_keys)):
        raise PlanValidationError("LimbSpec.key 必须唯一")
    nodes_by_key = {node.key: node for node in plan.nodes}
    for limb in plan.limbs:
        if not limb.key.strip():
            raise PlanValidationError("LimbSpec.key 不能为空")
        chains = (limb.bind_chain, limb.fk_chain, limb.ik_chain)
        if any(len(chain) != 3 for chain in chains):
            raise PlanValidationError(f"LimbSpec {limb.key!r} 的每条关节链必须正好包含三个节点")
        if len(limb.fk_controls) != 3 or len(set(limb.fk_controls)) != 3:
            raise PlanValidationError(f"LimbSpec {limb.key!r} 必须包含三个独立 FK 控制节点")
        referenced = (
            *limb.bind_chain,
            *limb.fk_chain,
            *limb.ik_chain,
            *limb.fk_controls,
            limb.ik_target,
            limb.pole_vector,
            limb.settings,
        )
        missing = [key for key in referenced if key not in nodes_by_key]
        if missing:
            raise PlanValidationError(f"LimbSpec {limb.key!r} 引用了不存在的节点：{', '.join(missing)}")
        chain_nodes = (*limb.bind_chain, *limb.fk_chain, *limb.ik_chain)
        if len(set(chain_nodes)) != 9:
            raise PlanValidationError(f"LimbSpec {limb.key!r} 的三条关节链必须彼此独立")
        if any(nodes_by_key[key].kind != "joint" for key in chain_nodes):
            raise PlanValidationError(f"LimbSpec {limb.key!r} 的 chain 节点必须都是 joint")
        if any(nodes_by_key[key].kind != "control" for key in limb.fk_controls):
            raise PlanValidationError(f"LimbSpec {limb.key!r} 的 FK 控制节点必须都是 control")
        for role, key in (
            ("IK target", limb.ik_target),
            ("Pole Vector", limb.pole_vector),
            ("settings", limb.settings),
        ):
            if nodes_by_key[key].kind == "joint":
                raise PlanValidationError(f"LimbSpec {limb.key!r} 的 {role} 不能是 joint")
        for chain in chains:
            if nodes_by_key[chain[1]].parent != chain[0] or nodes_by_key[chain[2]].parent != chain[1]:
                raise PlanValidationError(f"LimbSpec {limb.key!r} 的关节链父级关系不连续")
        if not re.fullmatch(r"[A-Za-z_]\w*", limb.blend_attribute):
            raise PlanValidationError(f"LimbSpec {limb.key!r} 的 blend 属性名非法")
