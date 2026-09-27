"""Host boundary for the Root HipSwinger branch without Inbetween Part."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_skeleton import FitDeformProfile
from adv_py.core.fit_hip_swing_no_parts import (
    HipSwingNoPartsPlan, HipSwingNoPartsTopology,
    plan_hip_swing_no_parts,
)
from adv_py.core.fit_inbetween_hip_swing import HipSwingFitSelection
from .body_character_rig import BodyCharacterRigBuildPlan


def character_hip_swing_no_parts_topology(
    rig: BodyCharacterRigBuildPlan,
) -> HipSwingNoPartsTopology:
    """Resolve real Root, Spine1 and LegLock receivers from the rig plan."""
    if rig.torso is None or rig.torso.torso.spine is None:
        raise ValueError("无分段 HipSwinger 需要标准 Spine IK 的 Torso 计划")
    torso = rig.torso.torso
    root = next((control for control in torso.controls.controls
                 if control.driven_joint == torso.pelvis_translation.target),
                None)
    spine1 = next((control for control in torso.controls.controls
                   if control.driven_joint == torso.spine.joints[1].path),
                  None)
    if root is None or spine1 is None:
        raise ValueError("无分段 HipSwinger 缺少 Root／Spine1 FK 控制")
    if (root.source_override_path != torso.root_fkx_path
            or torso.leg_lock.root_fkx_path != torso.root_fkx_path):
        raise ValueError("无分段 HipSwinger 的 Root FKX／LegLock 来源不一致")
    return HipSwingNoPartsTopology(
        fk_root_path=root.control_path,
        fk_root_offset_path=root.offset_path,
        root_fkx_path=torso.root_fkx_path,
        child_fk_offset_path=spine1.offset_path,
        leg_lock_matrix_input=torso.leg_lock.compensation_input,
        root_body_path=torso.pelvis_translation.target,
        child_body_path=torso.spine.body_joints[1],
    )


class HipSwingNoPartsHost(Protocol):
    """Create aligned transforms, the Root FKX constraint and matrix links.

    The host keeps the bind pose and disables translate, scale and shear on
    the inverse-rotation pickMatrix before connecting LegLock.
    """
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_hip_swing_no_parts(
        self, plan: HipSwingNoPartsPlan,
    ) -> None: ...
    def create_hip_swing_no_parts(
        self, plan: HipSwingNoPartsPlan,
    ) -> None: ...
    def capture_hip_swing_no_parts(
        self, plan: HipSwingNoPartsPlan,
    ) -> bool: ...


class BuildHipSwingNoParts:
    def __init__(self, host: HipSwingNoPartsHost) -> None:
        self._host = host

    def apply(self, selection: HipSwingFitSelection,
              topology: HipSwingNoPartsTopology, *,
              radius: float,
              root_profile: FitDeformProfile) -> HipSwingNoPartsPlan:
        plan = plan_hip_swing_no_parts(
            selection, topology, radius=radius,
            root_profile=root_profile)
        self._host.preflight_hip_swing_no_parts(plan)
        with self._host.transaction("构建无分段 Root HipSwinger"):
            self._host.create_hip_swing_no_parts(plan)
            if not self._host.capture_hip_swing_no_parts(plan):
                raise RuntimeError("无分段 Root HipSwinger 图不完整")
        return plan
