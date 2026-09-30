from dataclasses import dataclass
from typing import Protocol

from adv_py.core.body_build_options import BodyBuildOptions
from adv_py.core.body_torso import BodyTorsoLimbPlan, BodyTorsoPlan, BodyTorsoSnapshot, audit_body_torso, plan_body_torso
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_container import FitUpAxis
from .body_rebuild import BodyRebuildSafetyAudit


class BodyTorsoHost(Protocol):
    def scene_up_axis(self) -> FitUpAxis: ...
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
        arm: BodyTorsoLimbPlan, leg: BodyTorsoLimbPlan, *, radius: float = 1.5, spine_ik: bool = False, description=None, head_aim=False, aim_joint_names: frozenset[str] = frozenset(), fkx_joint_names: frozenset[str] | None = None, point_control_names: frozenset[str] | None = None, root_point_from_fkx: bool = True, axial_fk_root_point_from_receiver: bool = True,
    ) -> BodyTorsoBuildPlan:
        options={'up_axis':self._host.scene_up_axis()} if head_aim else {}
        metadata = {item.joint: item
                    for item in safety.symmetry.source.metadata}
        cog_names = tuple(item.output_name
                          for item in safety.symmetry.instances
                          if metadata[item.source_joint].cog)
        root_metadata = tuple(item for item in metadata.values()
                              if item.joint.rsplit("|", 1)[-1].rsplit(
                                  ":", 1)[-1] == "Root")
        if len(root_metadata) != 1:
            raise FitSkeletonValidationError(
                "Root Leg Lock 需要唯一的 Root Fit 关节")
        torso = plan_body_torso(
            safety.body, arm, leg, radius=radius, spine_ik=spine_ik,
            description=description, head_aim=head_aim,
            build_options=BodyBuildOptions.from_fit_settings(
                safety.symmetry.settings), cog_names=cog_names,
            aim_joint_names=aim_joint_names,
            fkx_joint_names=fkx_joint_names,
            point_control_names=point_control_names,
            root_point_from_fkx=root_point_from_fkx,
            axial_fk_root_point_from_receiver=(
                axial_fk_root_point_from_receiver),
            leg_lock_enabled=root_metadata[0].leg_lock is not False,
            **options)
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
