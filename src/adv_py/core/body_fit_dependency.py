"""Reject explicit Fit control target cycles before any Maya graph is built."""
from __future__ import annotations

from .body_fit_advanced_constraint import BodyFitAdvancedConstraintSpec
from .body_fit_follow import BodyFitFollowSpec


def validate_fit_control_dependencies(
    constraints: tuple[BodyFitAdvancedConstraintSpec, ...],
    follows: tuple[BodyFitFollowSpec, ...],
    named_edges: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> None:
    """A driven Body joint cannot depend on itself through Fit target links."""
    targets: dict[str, set[str]] = {}
    for spec in constraints:
        targets.setdefault(spec.source_body, set()).update(spec.target_joints)
    for spec in follows:
        outgoing = targets.setdefault(spec.source_body, set())
        outgoing.add(spec.primary_target)
        if spec.opposite_target is not None:
            outgoing.add(spec.opposite_target)
    for source_body, target_paths in named_edges:
        targets.setdefault(source_body, set()).update(target_paths)

    # Targets with no Fit controller cannot close a cycle in this graph.
    sources = set(targets)
    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(source: str) -> None:
        if source in visited:
            return
        if source in visiting:
            start = path.index(source)
            names = [item.rsplit("|", 1)[-1] for item in
                     path[start:] + [source]]
            raise ValueError("Fit 控制目标形成循环：" + " → ".join(names))
        visiting.add(source)
        path.append(source)
        for target in sorted(targets[source] & sources):
            visit(target)
        path.pop()
        visiting.remove(source)
        visited.add(source)

    for source in sorted(sources):
        visit(source)
