"""Describe an IK chain with Inbetween joints inside the solver topology.

    The ordinary rig is built before Fit Parts are inserted.  A solver
cannot be made equivalent to AdvancedSkeleton by placing follower joints beside
that chain: its handle must be rebuilt against the expanded parent chain.
This module describes that rewrite without invoking Maya.
"""
from __future__ import annotations

from dataclasses import dataclass

from .fit_inbetween_ik_parts import InbetweenIkPartsPlan


@dataclass(frozen=True, slots=True)
class InbetweenIkSolverJoint:
    name: str
    path: str
    parent_path: str
    source_body_part: str
    world_position: tuple[float, float, float]
    rotate_order: int


@dataclass(frozen=True, slots=True)
class InbetweenIkSolverPlan:
    handle_name: str
    effector_name: str
    solver_name: str
    handle_parent_path: str
    pole_control_path: str | None
    pole_constraint_name: str | None
    original_chain: tuple[str, ...]
    expanded_chain: tuple[str, ...]
    inserted_joints: tuple[InbetweenIkSolverJoint, ...]
    # Every original joint whose DAG path changes, in root-to-leaf order.
    path_rewrites: tuple[tuple[str, str], ...]

    @property
    def solved_joint_list(self) -> tuple[str, ...]:
        """Maya ikHandle -q -jointList excludes the end effector joint."""
        return self.expanded_chain[:-1]


def plan_inbetween_ik_solver(
    original_chain: tuple[str, ...],
    segments: tuple[InbetweenIkPartsPlan, ...],
    *,
    handle_name: str,
    effector_name: str,
    solver_name: str,
    handle_parent_path: str,
    pole_control_path: str | None,
    pole_constraint_name: str | None,
) -> InbetweenIkSolverPlan:
    """Expand all segments of one RP or single-chain handle as one rewrite.

    The caller supplies the complete original solver chain and every affected
    adjacent edge at once.  This avoids rebuilding the same handle twice and
    exposes the new DAG identities before any host operation occurs.
    """
    rp_solver = solver_name != "ikSCsolver"
    if (len(original_chain) < (3 if rp_solver else 2)
            or len(set(original_chain)) != len(original_chain)
            or any(not path.startswith("|") for path in original_chain)
            or any(not value for value in (
                handle_name, effector_name, solver_name, handle_parent_path))
            or (rp_solver and (not pole_control_path
                               or not pole_constraint_name))
            or (not rp_solver and (pole_control_path is not None
                                   or pole_constraint_name is not None))):
        raise ValueError("Inbetween IK 求解器缺少完整原始骨链或节点身份")
    if any(child.rsplit("|", 1)[0] != parent
           for parent, child in zip(original_chain, original_chain[1:])):
        raise ValueError("Inbetween IK 原始求解骨链不是直接父子")
    by_edge = {}
    for segment in segments:
        edge = (segment.start_ik_driver, segment.end_ik_driver)
        if (edge in by_edge or not segment.parts
                or any(part.parent_ikx_name != (
                    segment.start_ik_driver if index == 0
                    else segment.parts[index - 1].ikx_name)
                    for index, part in enumerate(segment.parts))):
            raise ValueError("Inbetween IK 段重复或 Part 父链不连续")
        by_edge[edge] = segment
    if not by_edge:
        raise ValueError("Inbetween IK 求解器缺少 Part 段")
    known_edges = set(zip(original_chain, original_chain[1:]))
    if not set(by_edge).issubset(known_edges):
        raise ValueError("Inbetween IK Part 段不在求解骨链中")

    expanded = [original_chain[0]]
    inserted = []
    rewrites = []
    parent = original_chain[0]
    seen_names = {path.rsplit("|", 1)[-1] for path in original_chain}
    for original_start, original_end in zip(original_chain, original_chain[1:]):
        segment = by_edge.get((original_start, original_end))
        if segment:
            for part in segment.parts:
                if part.ikx_name in seen_names:
                    raise ValueError("Inbetween IK Part 名称重复：" + part.ikx_name)
                seen_names.add(part.ikx_name)
                path = parent + "|" + part.ikx_name
                inserted.append(InbetweenIkSolverJoint(
                    part.ikx_name, path, parent, part.body_part_name,
                    part.world_position, part.rotate_order))
                expanded.append(path)
                parent = path
        original_end_name = original_end.rsplit("|", 1)[-1]
        new_end = parent + "|" + original_end_name
        if new_end != original_end:
            rewrites.append((original_end, new_end))
        expanded.append(new_end)
        parent = new_end
    return InbetweenIkSolverPlan(
        handle_name, effector_name, solver_name, handle_parent_path,
        pole_control_path, pole_constraint_name, original_chain,
        tuple(expanded), tuple(inserted), tuple(rewrites))
