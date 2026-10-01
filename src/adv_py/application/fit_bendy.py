"""Build source-shaped Bendy curve guides inside the character transaction."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Mapping, Protocol

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
    untwist_plug: str | None = None
    start_control_blend: bool = True
    end_matrix_follow: bool = True
    up_twist_plug: str | None = None

    def __post_init__(self) -> None:
        if self.untwist_plug is not None and not self.master_aim_follow:
            raise ValueError("旧版 Bendy 约束跟随不能接入新去扭转矩阵")
        if (self.end_matrix_follow and not self.master_aim_follow
                and not self.chain.child_start_influence):
            raise ValueError("旧版 Bendy 主控与新版末端矩阵不能混搭")
        if self.chain.micro_up_twist and not self.up_twist_plug:
            raise ValueError("Bendy 双向扭转缺少子段来源")

    @property
    def node_names(self) -> tuple[str, ...]:
        names = self.chain.follow_node_names
        if not self.master_aim_follow:
            return names
        master_constraint = ("AdvPy_" + self.chain.control_names[0]
                             + "Follow")
        end_constraint = ("AdvPy_" + self.chain.end_proxy_name
                          + "Follow")
        return (tuple(name for name in names
                      if name != master_constraint
                      and (not self.end_matrix_follow
                           or name != end_constraint))
                + self.chain.master_follow_matrix_names
                + (self.chain.parent_untwist_names
                   if self.untwist_plug else ())
                + (self.chain.end_follow_matrix_names
                   if (self.end_matrix_follow
                       and not self.chain.child_start_influence)
                   else ()))


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
    rig: BodyCharacterRigBuildPlan | None,
    generic_controls: tuple[BodyLimbFkControlSpec, ...] = (),
    generic_endpoints: tuple[BodyGenericFkEndpointSpec, ...] = (),
    master_aim_sources: frozenset[str] | None = None,
    untwist_plugs: Mapping[str, str] | None = None,
    up_twist_plugs: Mapping[str, str] | None = None,
    start_control_sources: frozenset[str] | None = None,
    child_control_sources: frozenset[str] | None = None,
    untwist_sources: frozenset[str] | None = None,
    end_matrix_sources: frozenset[str] | None = None,
    resolved_world_sources: Mapping[str, FitBendyWorldSource] | None = None,
) -> tuple[FitBendyFollowSpec, ...]:
    """Resolve Bendy endpoints without depending on driven Body matrices."""
    if resolved_world_sources is None:
        if rig is None:
            raise ValueError("Bendy 需要真实 Rig 或已解析的独立矩阵来源")
        sources = fit_bendy_world_sources(rig, generic_controls, generic_endpoints)
    else:
        sources = dict(resolved_world_sources)
    child_chains = {chain.start_body: chain for chain in chains}
    result = []
    for chain in chains:
        start = sources.get(chain.start_body)
        end = sources.get(chain.end_body)
        if (chain.end_body in child_chains
                and (child_control_sources is None
                     or chain.control_names[0]
                     in child_control_sources)):
            child = child_chains[chain.end_body]
            end = FitBendyWorldSource(
                (child.control_names[1]
                 if child.legacy_twist_outputs else
                 child.twist_projection_names[1][0])
                + ".worldMatrix[0]")
        if start is None or end is None:
            raise ValueError("Bendy 端点缺少独立 Rig 来源："
                             + chain.start_body + " → " + chain.end_body)
        driven_names = frozenset(
            path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            for path in (chain.start_body, *chain.part_names,
                         chain.end_body))
        for source in (start, end):
            if (source.ik_matrix is None) != (source.blend_plug is None):
                raise ValueError("Bendy IK/FK 来源不完整：" + chain.curve_name)
            for plug in (source.fk_matrix, source.ik_matrix):
                if plug is None:
                    continue
                node = plug.split(".", 1)[0].rsplit("|", 1)[-1]
                if node.rsplit(":", 1)[-1] in driven_names:
                    raise ValueError("Bendy 端点不能回读受驱动 Body／Part："
                                     + plug)
        twist_plug = (untwist_plugs or {}).get(chain.start_body)
        up_plug = (up_twist_plugs or {}).get(chain.start_body)
        for plug in (twist_plug, up_plug):
            if plug:
                node = plug.split(".", 1)[0].rsplit("|", 1)[-1]
                if node.rsplit(":", 1)[-1] in driven_names:
                    raise ValueError("Bendy 扭转不能回读受驱动 Body／Part："
                                     + plug)
        result.append(FitBendyFollowSpec(
            chain, start, end,
            master_aim_sources is None
            or chain.control_names[0] in master_aim_sources,
            (untwist_plugs or {}).get(chain.start_body)
            if (master_aim_sources is None
                or chain.control_names[0] in master_aim_sources)
            and (untwist_sources is None
                 or chain.control_names[0] in untwist_sources)
            else None,
            start_control_sources is None
            or chain.control_names[0] in start_control_sources,
            end_matrix_sources is None
            or chain.control_names[0] in end_matrix_sources,
            up_plug
            if chain.micro_up_twist else None))
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
        self, spec: FitBendyFollowSpec,
        planned_sources: frozenset[str] = frozenset(),
    ) -> None: ...
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
        self, spec: FitBendyChainSpec,
        base_twist_plug: str | None = None,
        up_twist_plug: str | None = None) -> None: ...
    def capture_fit_bendy_micro(
        self, spec: FitBendyChainSpec,
        base_twist_plug: str | None = None,
        up_twist_plug: str | None = None) -> bool: ...
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
        if len({chain.scale_guide_group for chain in chains}) > 1:
            raise ValueError("Bendy 导向关节组不能混用缩放策略")
        used = set()
        for chain in chains:
            names = set(chain.guide_node_names)
            if names & used:
                raise ValueError("Fit Bendy 导向节点名称重复")
            used.update(names)
            self._host.preflight_fit_bendy_guides(chain)
        planned_sources = frozenset(
            name + ".worldMatrix[0]"
            for chain in chains for name in (
                chain.control_names[1],
                chain.twist_projection_names[1][0]))
        for follow in follows:
            if follow.chain.micro_base_twist and not follow.untwist_plug:
                raise ValueError("Bendy 微控制缺少独立基础扭转来源："
                                 + follow.chain.curve_name)
            if follow.chain.micro_up_twist and not follow.up_twist_plug:
                raise ValueError("Bendy 微控制缺少上行扭转来源："
                                 + follow.chain.curve_name)
            names = set(follow.node_names)
            if names & used:
                raise ValueError("Fit Bendy 跟随节点名称重复")
            used.update(names)
            self._host.preflight_fit_bendy_follow(
                follow, planned_sources)
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
                self._host.create_fit_bendy_micro(
                    follow.chain, follow.untwist_plug,
                    follow.up_twist_plug)
            for chain in chains:
                if not self._host.capture_fit_bendy_guides(chain):
                    raise RuntimeError("Bendy 曲线导向接线不一致："
                                       + chain.curve_name)
            for follow in follows:
                if not self._host.capture_fit_bendy_follow(follow):
                    raise RuntimeError("Bendy 独立驱动接线不一致："
                                       + follow.chain.curve_name)
                if not self._host.capture_fit_bendy_micro(
                        follow.chain, follow.untwist_plug,
                        follow.up_twist_plug):
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
