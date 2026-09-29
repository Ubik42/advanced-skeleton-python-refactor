"""Build source-shaped Bendy curve guides inside the character transaction."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_bendy import FitBendyChainSpec, FitBendyFkScaleSpec
from adv_py.core.body_limb_controls import BodyLimbFkControlSpec
from adv_py.core.body_generic_fk import BodyGenericFkEndpointSpec
from .body_character_rig import BodyCharacterRigBuildPlan


@dataclass(frozen=True, slots=True)
class FitBendyWorldSource:
    """Independent world frame; optional IK matrix is mixed by blend_plug."""

    fk_matrix: str
    ik_matrix: str | None = None
    blend_plug: str | None = None

    def __post_init__(self) -> None:
        if not self.fk_matrix or ((self.ik_matrix is None)
                                  != (self.blend_plug is None)):
            raise ValueError("Bendy 独立矩阵来源不完整")


@dataclass(frozen=True, slots=True)
class FitBendyFollowSpec:
    chain: FitBendyChainSpec
    start: FitBendyWorldSource
    end: FitBendyWorldSource
    master_aim_follow: bool = True

    @property
    def node_names(self) -> tuple[str, ...]:
        names = self.chain.follow_node_names
        if not self.master_aim_follow:
            return names
        master_constraint = ("AdvPy_" + self.chain.control_names[0]
                             + "Follow")
        return tuple(name for name in names
                     if name != master_constraint) + (
                         self.chain.master_follow_matrix_names)


def fit_bendy_world_sources(
    rig: BodyCharacterRigBuildPlan,
    generic_controls: tuple[BodyLimbFkControlSpec, ...] = (),
    generic_endpoints: tuple[BodyGenericFkEndpointSpec, ...] = (),
) -> dict[str, FitBendyWorldSource]:
    """Resolve available independent frames without reading driven Body."""
    # The same direct-control and spine mechanism map drives ordinary Part twist.
    from .registered_body_build import _independent_rig_twist_sources

    controls, _, spines = _independent_rig_twist_sources(rig)
    sources = {body: FitBendyWorldSource(matrix)
               for body, matrix in controls.items()}
    for body, (fk, ik, blend, _) in spines.items():
        sources[body] = FitBendyWorldSource(fk, ik, blend)
    for limb in (rig.arm, rig.leg):
        for side in limb.blend.sides:
            blend = limb.blend.settings_path + "." + side.attribute
            for joint in side.joints:
                if joint.body_joint in sources:
                    raise ValueError("Bendy Body 独立来源重复：" + joint.body_joint)
                sources[joint.body_joint] = FitBendyWorldSource(
                    joint.fk_driver + ".worldMatrix[0]",
                    joint.ik_driver + ".worldMatrix[0]", blend)
    for control in generic_controls:
        if control.driven_joint in sources:
            raise ValueError("Bendy 通用 FK 来源与标准来源重复："
                             + control.driven_joint)
        source = (control.source_override_path
                  or control.sub_control_path or control.control_path)
        sources[control.driven_joint] = FitBendyWorldSource(
            source + ".worldMatrix[0]")
    for endpoint in generic_endpoints:
        if endpoint.driven_joint in sources:
            raise ValueError("Bendy 末端 FK 参照与已有来源重复："
                             + endpoint.driven_joint)
        sources[endpoint.driven_joint] = FitBendyWorldSource(
            endpoint.path + ".worldMatrix[0]")
    return sources


def split_fit_bendy_chains(
    chains: tuple[FitBendyChainSpec, ...],
    rig: BodyCharacterRigBuildPlan,
) -> tuple[tuple[FitBendyChainSpec, ...],
           tuple[FitBendyChainSpec, ...]]:
    """Defer an entire connected Bendy component needing generic FK."""
    available = set(fit_bendy_world_sources(rig))
    deferred_bodies = {
        body for chain in chains
        for body in (chain.start_body, chain.end_body)
        if body not in available}
    changed = True
    while changed:
        before = len(deferred_bodies)
        for chain in chains:
            if (chain.start_body in deferred_bodies
                    or chain.end_body in deferred_bodies):
                deferred_bodies.update((chain.start_body, chain.end_body))
        changed = len(deferred_bodies) != before
    early = tuple(chain for chain in chains
                  if chain.start_body not in deferred_bodies)
    later = tuple(chain for chain in chains
                  if chain.start_body in deferred_bodies)
    return early, later


def plan_fit_bendy_follow(
    chains: tuple[FitBendyChainSpec, ...],
    rig: BodyCharacterRigBuildPlan,
    generic_controls: tuple[BodyLimbFkControlSpec, ...] = (),
    generic_endpoints: tuple[BodyGenericFkEndpointSpec, ...] = (),
    master_aim_sources: frozenset[str] | None = None,
) -> tuple[FitBendyFollowSpec, ...]:
    """Resolve Bendy endpoints without depending on driven Body matrices."""
    sources = fit_bendy_world_sources(
        rig, generic_controls, generic_endpoints)
    result = []
    for chain in chains:
        start = sources.get(chain.start_body)
        end = sources.get(chain.end_body)
        if start is None or end is None:
            raise ValueError("Bendy 端点缺少独立 Rig 来源："
                             + chain.start_body + " → " + chain.end_body)
        for source in (start, end):
            if (source.ik_matrix is None) != (source.blend_plug is None):
                raise ValueError("Bendy IK/FK 来源不完整：" + chain.curve_name)
        result.append(FitBendyFollowSpec(
            chain, start, end,
            master_aim_sources is None
            or chain.control_names[0] in master_aim_sources))
    return tuple(result)


class FitBendyGuideHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_fit_bendy_guides(
        self, spec: FitBendyChainSpec) -> None: ...
    def create_fit_bendy_guides(
        self, spec: FitBendyChainSpec) -> None: ...
    def capture_fit_bendy_guides(
        self, spec: FitBendyChainSpec) -> bool: ...
    def preflight_fit_bendy_follow(
        self, spec: FitBendyFollowSpec) -> None: ...
    def create_fit_bendy_follow(
        self, spec: FitBendyFollowSpec) -> None: ...
    def capture_fit_bendy_follow(
        self, spec: FitBendyFollowSpec) -> bool: ...
    def create_fit_bendy_circular(
        self, spec: FitBendyChainSpec) -> None: ...
    def capture_fit_bendy_circular(
        self, spec: FitBendyChainSpec) -> bool: ...
    def preflight_fit_bendy_micro(
        self, spec: FitBendyChainSpec) -> None: ...
    def create_fit_bendy_micro(
        self, spec: FitBendyChainSpec) -> None: ...
    def capture_fit_bendy_micro(
        self, spec: FitBendyChainSpec) -> bool: ...
    def preflight_fit_bendy_secondary(
        self, spec: FitBendyChainSpec) -> None: ...
    def create_fit_bendy_secondary(
        self, spec: FitBendyChainSpec) -> None: ...
    def capture_fit_bendy_secondary(
        self, spec: FitBendyChainSpec) -> bool: ...
    def create_fit_bendy_twist_projections(
        self, spec: FitBendyChainSpec) -> None: ...


class BuildFitBendyGuides:
    def __init__(self, host: FitBendyGuideHost) -> None:
        self._host = host

    def apply(self, chains: tuple[FitBendyChainSpec, ...], *,
              follows: tuple[FitBendyFollowSpec, ...] = ()
              ) -> tuple[FitBendyChainSpec, ...]:
        if follows and tuple(item.chain for item in follows) != chains:
            raise ValueError("Bendy 跟随链与曲线链不一致")
        used = set()
        for chain in chains:
            names = set(chain.guide_node_names)
            if names & used:
                raise ValueError("Fit Bendy 导向节点名称重复")
            used.update(names)
            self._host.preflight_fit_bendy_guides(chain)
        for follow in follows:
            names = set(follow.node_names)
            if names & used:
                raise ValueError("Fit Bendy 跟随节点名称重复")
            used.update(names)
            self._host.preflight_fit_bendy_follow(follow)
            micro_names = set(follow.chain.micro_node_names)
            if micro_names & used:
                raise ValueError("Fit Bendy 微控制节点名称重复")
            used.update(micro_names)
            self._host.preflight_fit_bendy_micro(follow.chain)
            secondary_names = set(follow.chain.secondary_node_names)
            if secondary_names & used:
                raise ValueError("Fit Bendy 第二曲线节点名称重复")
            used.update(secondary_names)
            self._host.preflight_fit_bendy_secondary(follow.chain)
        with self._host.transaction("创建 Bendy 曲线导向"):
            for chain in chains:
                self._host.create_fit_bendy_guides(chain)
            for follow in follows:
                self._host.create_fit_bendy_follow(follow)
            for follow in follows:
                self._host.create_fit_bendy_circular(follow.chain)
            for follow in follows:
                self._host.create_fit_bendy_secondary(follow.chain)
            for follow in follows:
                self._host.create_fit_bendy_twist_projections(follow.chain)
            for follow in follows:
                self._host.create_fit_bendy_micro(follow.chain)
            for chain in chains:
                if not self._host.capture_fit_bendy_guides(chain):
                    raise RuntimeError("Bendy 曲线导向接线不一致："
                                       + chain.curve_name)
            for follow in follows:
                if not self._host.capture_fit_bendy_follow(follow):
                    raise RuntimeError("Bendy 独立驱动接线不一致："
                                       + follow.chain.curve_name)
                if not self._host.capture_fit_bendy_micro(follow.chain):
                    raise RuntimeError("Bendy 微控制接线不一致："
                                       + follow.chain.curve_name)
                if not self._host.capture_fit_bendy_secondary(follow.chain):
                    raise RuntimeError("Bendy 第二曲线接线不一致："
                                       + follow.chain.secondary_curve_name)
                if not self._host.capture_fit_bendy_circular(follow.chain):
                    raise RuntimeError("Bendy 交界 Circular 接线不一致："
                                       + follow.chain.curve_name)
        return chains


class FitBendyDeformHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_fit_bendy_deform(
        self, spec: FitBendyChainSpec) -> None: ...
    def connect_fit_bendy_deform(
        self, spec: FitBendyChainSpec) -> None: ...
    def capture_fit_bendy_deform(
        self, spec: FitBendyChainSpec) -> bool: ...


class BuildFitBendyDeform:
    """Replace ordinary Body/Part TR drivers with Bendy micro outputs."""

    def __init__(self, host: FitBendyDeformHost) -> None:
        self._host = host

    def apply(self, chains: tuple[FitBendyChainSpec, ...]
              ) -> tuple[FitBendyChainSpec, ...]:
        deformers = [name for chain in chains
                     for name in chain.deform_names]
        if len(set(deformers)) != len(deformers):
            raise ValueError("Bendy 变形关节被多条曲线重复接管")
        constraints = [name for chain in chains
                       for name in chain.deform_constraint_names]
        if len(set(constraints)) != len(constraints):
            raise ValueError("Bendy 变形约束名称重复")
        for chain in chains:
            self._host.preflight_fit_bendy_deform(chain)
        with self._host.transaction("Bendy Micro 接管 Body／Part"):
            for chain in chains:
                self._host.connect_fit_bendy_deform(chain)
            for chain in chains:
                if not self._host.capture_fit_bendy_deform(chain):
                    raise RuntimeError("Bendy 变形关节未由 Micro 驱动："
                                       + chain.curve_name)
        return chains


class FitBendyFkScaleHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_fit_bendy_fk_scale(
        self, spec: FitBendyFkScaleSpec) -> None: ...
    def connect_fit_bendy_fk_scale(
        self, spec: FitBendyFkScaleSpec) -> None: ...
    def capture_fit_bendy_fk_scale(
        self, spec: FitBendyFkScaleSpec) -> bool: ...


class BuildFitBendyFkScales:
    def __init__(self, host: FitBendyFkScaleHost) -> None:
        self._host = host

    def apply(self, specs: tuple[FitBendyFkScaleSpec, ...]
              ) -> tuple[FitBendyFkScaleSpec, ...]:
        for spec in specs:
            self._host.preflight_fit_bendy_fk_scale(spec)
        with self._host.transaction("连接通用 Bendy 的 FK 缩放"):
            for spec in specs:
                self._host.connect_fit_bendy_fk_scale(spec)
            for spec in specs:
                if not self._host.capture_fit_bendy_fk_scale(spec):
                    raise RuntimeError("通用 Bendy FK 缩放接线不一致："
                                       + spec.body_joint)
        return specs
