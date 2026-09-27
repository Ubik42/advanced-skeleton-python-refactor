"""Host boundary for replacing a solved RP chain with its Inbetween topology."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_inbetween_ik_parts import InbetweenIkPartsPlan
from adv_py.core.fit_inbetween_ik_solver import (
    InbetweenIkSolverPlan, plan_inbetween_ik_solver,
)


class InbetweenIkSolverHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_inbetween_ik_solver(self, plan: InbetweenIkSolverPlan) -> None:
        """Check ownership, unique names, rest pose, solver and external links."""
        ...

    def remove_inbetween_ik_solver(self, plan: InbetweenIkSolverPlan) -> None:
        """Remove only the owned handle, effector and pole constraint."""
        ...

    def insert_inbetween_ik_solver_segment(
        self, plan: InbetweenIkSolverPlan,
        segment: InbetweenIkPartsPlan,
    ) -> None:
        """Create Part joints and reparent the end joint, preserving world pose.

        Segments arrive leaf-first, so original source paths still exist when
        each edge is rewritten.  New joints use their Fit Part rest positions,
        not a dynamic fraction of the old endpoint translate channel.
        """
        ...

    def restore_inbetween_ik_solver(self, plan: InbetweenIkSolverPlan) -> None:
        """Create the handle over expanded_chain and reconnect pole/parent."""
        ...

    def capture_inbetween_ik_solver(self, plan: InbetweenIkSolverPlan) -> bool:
        """Compare full DAG chain, solver, handle parent and pole source."""
        ...


class BuildInbetweenIkSolver:
    def __init__(self, host: InbetweenIkSolverHost) -> None:
        self._host = host

    def apply(
        self,
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
        plan = plan_inbetween_ik_solver(
            original_chain, segments, handle_name=handle_name,
            effector_name=effector_name, solver_name=solver_name,
            handle_parent_path=handle_parent_path,
            pole_control_path=pole_control_path,
            pole_constraint_name=pole_constraint_name)
        self._host.preflight_inbetween_ik_solver(plan)
        segments_by_edge = {
            (segment.start_ik_driver, segment.end_ik_driver): segment
            for segment in segments
        }
        with self._host.transaction("重建 Inbetween IK 求解链"):
            self._host.remove_inbetween_ik_solver(plan)
            for edge in reversed(tuple(zip(original_chain, original_chain[1:]))):
                segment = segments_by_edge.get(edge)
                if segment is not None:
                    self._host.insert_inbetween_ik_solver_segment(plan, segment)
            self._host.restore_inbetween_ik_solver(plan)
            if not self._host.capture_inbetween_ik_solver(plan):
                raise RuntimeError("Inbetween IK 求解链重建结果不完整："
                                   + plan.handle_name)
        return plan
