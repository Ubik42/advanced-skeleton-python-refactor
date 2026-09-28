"""Build source-shaped Bendy curve guides inside the character transaction."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_bendy import FitBendyChainSpec
from .body_character_rig import BodyCharacterRigBuildPlan


@dataclass(frozen=True, slots=True)
class FitBendyWorldSource:
    """Independent world frame; optional IK matrix is mixed by blend_plug."""

    fk_matrix: str
    ik_matrix: str | None = None
    blend_plug: str | None = None


@dataclass(frozen=True, slots=True)
class FitBendyFollowSpec:
    chain: FitBendyChainSpec
    start: FitBendyWorldSource
    end: FitBendyWorldSource


def plan_fit_bendy_follow(
    chains: tuple[FitBendyChainSpec, ...],
    rig: BodyCharacterRigBuildPlan,
) -> tuple[FitBendyFollowSpec, ...]:
    """Resolve Bendy endpoints without depending on driven Body matrices."""
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
        result.append(FitBendyFollowSpec(chain, start, end))
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
    def preflight_fit_bendy_micro(
        self, spec: FitBendyChainSpec) -> None: ...
    def create_fit_bendy_micro(
        self, spec: FitBendyChainSpec) -> None: ...
    def capture_fit_bendy_micro(
        self, spec: FitBendyChainSpec) -> bool: ...


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
            names = set(follow.chain.follow_node_names)
            if names & used:
                raise ValueError("Fit Bendy 跟随节点名称重复")
            used.update(names)
            self._host.preflight_fit_bendy_follow(follow)
            micro_names = set(follow.chain.micro_node_names)
            if micro_names & used:
                raise ValueError("Fit Bendy 微控制节点名称重复")
            used.update(micro_names)
            self._host.preflight_fit_bendy_micro(follow.chain)
        with self._host.transaction("创建 Bendy 曲线导向"):
            for chain in chains:
                self._host.create_fit_bendy_guides(chain)
            for follow in follows:
                self._host.create_fit_bendy_follow(follow)
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
