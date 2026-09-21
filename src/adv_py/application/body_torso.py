from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_torso import BodyTorsoLimbPlan, BodyTorsoPlan, BodyTorsoSnapshot, audit_body_torso, plan_body_torso
from adv_py.core.fit_settings import FitSkeletonValidationError
from .body_rebuild import BodyRebuildSafetyAudit


class BodyTorsoHost(Protocol):
    def find_name_collisions(self, name: str) -> tuple[str, ...]: ...
    def preflight_body_torso(self, plan: BodyTorsoPlan) -> None: ...
    def create_body_torso(self, plan: BodyTorsoPlan) -> None: ...
    def capture_body_torso(self, plan: BodyTorsoPlan) -> BodyTorsoSnapshot: ...


@dataclass(frozen=True, slots=True)
class BodyTorsoBuildPlan:
    safety: BodyRebuildSafetyAudit
    torso: BodyTorsoPlan
    name_collisions: tuple[str, ...]

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(issue.message for issue in self.safety.issues) + tuple(
            f"Torso 节点名称冲突：{name}" for name in self.name_collisions
        )

    @property
    def ready(self) -> bool:
        return not self.blockers


class BuildBodyTorso:
    """Torso and limb attachments are assembled by the character transaction."""

    def __init__(self, host: BodyTorsoHost) -> None:
        self._host = host

    def plan_from_safety(
        self, safety: BodyRebuildSafetyAudit,
        arm: BodyTorsoLimbPlan, leg: BodyTorsoLimbPlan, *, radius: float = 2.0, spine_ik: bool = False,
    ) -> BodyTorsoBuildPlan:
        torso = plan_body_torso(safety.body, arm, leg, radius=radius, spine_ik=spine_ik)
        collisions = tuple(sorted({path for name in torso.node_names for path in self._host.find_name_collisions(name)}))
        self._host.preflight_body_torso(torso)
        return BodyTorsoBuildPlan(safety, torso, collisions)

    def build_in_transaction(self, plan: BodyTorsoBuildPlan) -> BodyTorsoSnapshot:
        if not plan.ready:
            raise FitSkeletonValidationError("；".join(plan.blockers))
        self._host.create_body_torso(plan.torso)
        snapshot = self._host.capture_body_torso(plan.torso)
        issues = audit_body_torso(plan.torso, snapshot)
        if issues:
            raise RuntimeError("；".join(issues))
        return snapshot
