"""Connect non-OPM Fit Part scale to resolved body or limb controls."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_skeleton import BodyJointSpec
from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_part_scale import (
    FitPartEndScale, FitPartInheritedScaleChain, FitPartLimbScaleChain,
    FitPartScalePlan, FitPartScaleStep, FitPartToeScale,
    plan_fit_part_scale,
)


class FitPartScaleHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def inspect_fit_part_inherited_scale(
        self, chain: FitPartInheritedScaleChain) -> bool: ...

    def preflight_fit_part_scale(self, step: FitPartScaleStep) -> None: ...

    def connect_fit_part_scale(self, step: FitPartScaleStep) -> None: ...

    def capture_fit_part_scale_source(
        self, step: FitPartScaleStep
    ) -> str | None: ...

    def preflight_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> None: ...

    def connect_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> None: ...

    def capture_fit_part_limb_scale(
        self, chain: FitPartLimbScaleChain
    ) -> bool: ...

    def preflight_fit_part_end_scale(self, end: FitPartEndScale) -> None: ...

    def connect_fit_part_end_scale(self, end: FitPartEndScale) -> None: ...

    def capture_fit_part_end_scale(self, end: FitPartEndScale) -> bool: ...

    def preflight_fit_part_toe_scale(self, toe: FitPartToeScale) -> None: ...

    def connect_fit_part_toe_scale(self, toe: FitPartToeScale) -> None: ...

    def capture_fit_part_toe_scale(self, toe: FitPartToeScale) -> bool: ...


class BuildFitPartScaleDrivers:
    def __init__(self, host: FitPartScaleHost) -> None:
        self._host = host

    def apply(
        self, parts: tuple[FitPartJointSpec, ...],
        body_joints: tuple[BodyJointSpec, ...] = (),
        ik_local_sources: frozenset[str] = frozenset(),
        leg_fk_control_names: frozenset[str] = frozenset(),
    ) -> FitPartScalePlan:
        plan = plan_fit_part_scale(parts, body_joints, ik_local_sources,
                                   leg_fk_control_names)
        for step in plan.direct:
            self._host.preflight_fit_part_scale(step)
        for chain in plan.limbs:
            self._host.preflight_fit_part_limb_scale(chain)
        for end in plan.ends:
            self._host.preflight_fit_part_end_scale(end)
        for toe in plan.toes:
            self._host.preflight_fit_part_toe_scale(toe)
        for chain in plan.inherited:
            if not self._host.inspect_fit_part_inherited_scale(chain):
                raise ValueError("Fit Part OPM 缩放父链无效："
                                 + chain.start_body_name)
        with self._host.transaction("构建 Fit Part 缩放驱动"):
            for step in plan.direct:
                self._host.connect_fit_part_scale(step)
            for chain in plan.limbs:
                self._host.connect_fit_part_limb_scale(chain)
            for end in plan.ends:
                self._host.connect_fit_part_end_scale(end)
            for toe in plan.toes:
                self._host.connect_fit_part_toe_scale(toe)
            for step in plan.direct:
                if self._host.capture_fit_part_scale_source(step) != step.source_plug:
                    raise RuntimeError("Fit Part 缩放输出连接不一致：" + step.part_name)
            for chain in plan.limbs:
                if not self._host.capture_fit_part_limb_scale(chain):
                    raise RuntimeError("Fit Part 四肢缩放连接不一致："
                                       + chain.start_body_name)
            for end in plan.ends:
                if not self._host.capture_fit_part_end_scale(end):
                    raise RuntimeError("Fit Part 末端缩放连接不一致："
                                       + end.body_name)
            for toe in plan.toes:
                if not self._host.capture_fit_part_toe_scale(toe):
                    raise RuntimeError("Fit Part 脚趾缩放连接不一致："
                                       + toe.body_name)
            for chain in plan.inherited:
                if not self._host.inspect_fit_part_inherited_scale(chain):
                    raise RuntimeError("Fit Part OPM 缩放父链改变："
                                       + chain.start_body_name)
        return plan
