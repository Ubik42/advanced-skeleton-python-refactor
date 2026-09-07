from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.model import RigPlan
from adv_py.core.validation import validate_plan

from .ports import RigHost


@dataclass(frozen=True, slots=True)
class BuildResult:
    host: str
    plan: str
    created_nodes: int
    created_constraints: int
    dry_run: bool


class BuildRig:
    """Validate once, mutate inside one host-owned transaction, verify afterwards."""

    def __init__(self, host: RigHost) -> None:
        self._host = host

    def execute(self, plan: RigPlan, *, dry_run: bool = False) -> BuildResult:
        validate_plan(plan)
        preflight_errors = self._host.preflight(plan)
        if preflight_errors:
            raise RuntimeError("预检失败：" + "；".join(preflight_errors))

        if not dry_run:
            with self._host.transaction(f"构建 {plan.name}"):
                for node in plan.nodes:
                    self._host.create_node(node)
                for node in plan.nodes:
                    if node.parent is not None:
                        self._host.parent_node(node.key, node.parent)
                for constraint in plan.constraints:
                    self._host.create_constraint(constraint)
                verification_errors = self._host.verify(plan)
                if verification_errors:
                    raise RuntimeError("构建后复检失败：" + "；".join(verification_errors))

        return BuildResult(
            host=self._host.name,
            plan=plan.name,
            created_nodes=0 if dry_run else len(plan.nodes),
            created_constraints=0 if dry_run else len(plan.constraints),
            dry_run=dry_run,
        )
