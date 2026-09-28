"""Restore expanded limb mechanism paths for post-build actions."""
from __future__ import annotations

from typing import Protocol

from adv_py.core.body_arm_mechanisms import (
    BodyArmMechanismPlan, BodyArmMechanismSnapshot,
    plan_body_arm_mechanisms,
)
from adv_py.core.body_leg_mechanisms import (
    BodyLegMechanismPlan, BodyLegMechanismSnapshot,
    plan_body_leg_mechanisms,
)
from adv_py.core.body_limb_mechanisms import recover_body_limb_mechanisms
from adv_py.core.body_skeleton import BodySkeletonSnapshot


class BodyArmMechanismRecoveryHost(Protocol):
    def capture_body_arm_mechanisms(
        self, plan: BodyArmMechanismPlan,
    ) -> BodyArmMechanismSnapshot: ...


class BodyLegMechanismRecoveryHost(Protocol):
    def capture_body_leg_mechanisms(
        self, plan: BodyLegMechanismPlan,
    ) -> BodyLegMechanismSnapshot: ...


def plan_existing_body_arm_mechanisms(
    host: BodyArmMechanismRecoveryHost,
    body: BodySkeletonSnapshot,
) -> BodyArmMechanismPlan:
    base = plan_body_arm_mechanisms(body, allow_part_parents=True)
    snapshot = host.capture_body_arm_mechanisms(base)
    return recover_body_limb_mechanisms(base, body, snapshot)


def plan_existing_body_leg_mechanisms(
    host: BodyLegMechanismRecoveryHost,
    body: BodySkeletonSnapshot,
) -> BodyLegMechanismPlan:
    base = plan_body_leg_mechanisms(body, allow_part_parents=True)
    snapshot = host.capture_body_leg_mechanisms(base)
    return recover_body_limb_mechanisms(base, body, snapshot)
