"""Create the lower-Outer auxiliary influence through a scene port."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.face_lower_outer_auxiliary import (
    FaceLowerOuterAuxiliaryInput, FaceLowerOuterAuxiliaryPlan,
    plan_face_lower_outer_auxiliary,
)


class FaceLowerOuterAuxiliaryHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def capture_lower_outer_auxiliary_input(
        self, side: str, simpler_eyelid: bool,
    ) -> FaceLowerOuterAuxiliaryInput: ...
    def preflight_lower_outer_auxiliary(
        self, plan: FaceLowerOuterAuxiliaryPlan,
    ) -> None: ...
    def create_lower_outer_auxiliary(
        self, plan: FaceLowerOuterAuxiliaryPlan,
    ) -> None: ...
    def set_lower_outer_auxiliary_seed_weight(
        self, plan: FaceLowerOuterAuxiliaryPlan, weight: float,
    ) -> None: ...
    def smooth_lower_outer_auxiliary_weights(
        self, plan: FaceLowerOuterAuxiliaryPlan,
        vertices: tuple[int, ...],
    ) -> None: ...
    def capture_lower_outer_auxiliary(
        self, plan: FaceLowerOuterAuxiliaryPlan,
    ) -> bool: ...


class BuildFaceLowerOuterAuxiliary:
    def __init__(self, host: FaceLowerOuterAuxiliaryHost) -> None:
        self._host = host

    def plan(self, side: str, *,
             simpler_eyelid: bool) -> FaceLowerOuterAuxiliaryPlan | None:
        if type(simpler_eyelid) is not bool:
            raise ValueError("简化眼睑模式必须是布尔值")
        if not simpler_eyelid:
            return None
        source = self._host.capture_lower_outer_auxiliary_input(
            side, simpler_eyelid)
        plan = plan_face_lower_outer_auxiliary(source)
        if plan is not None:
            self._host.preflight_lower_outer_auxiliary(plan)
        return plan

    def apply(self, side: str, *,
              simpler_eyelid: bool) -> FaceLowerOuterAuxiliaryPlan | None:
        plan = self.plan(side, simpler_eyelid=simpler_eyelid)
        if plan is None:
            return None
        with self._host.transaction("构建眼下外围辅助关节"):
            self.apply_in_transaction(plan)
        return plan

    def apply_in_transaction(
        self, plan: FaceLowerOuterAuxiliaryPlan,
    ) -> None:
        self._host.create_lower_outer_auxiliary(plan)
        self._host.set_lower_outer_auxiliary_seed_weight(plan, 1.)
        if plan.smooth_vertices:
            self._host.smooth_lower_outer_auxiliary_weights(
                plan, plan.smooth_vertices)
        self._host.smooth_lower_outer_auxiliary_weights(
            plan, (plan.seed_vertex,))
        self._host.set_lower_outer_auxiliary_seed_weight(
            plan, plan.seed_weight)
        if not self._host.capture_lower_outer_auxiliary(plan):
            raise RuntimeError("眼下外围辅助关节或 Skin 权重不完整")
