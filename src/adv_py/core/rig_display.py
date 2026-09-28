"""Scene display commands corresponding to ADV 6.925's Display panel."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class RigDisplayState:
    motion_visibility: bool | None
    joint_visibility: bool | None
    joint_visibility_plug: str | None
    joint_axes: tuple[tuple[str, bool], ...]
    joint_size: float
    legacy_root_visibility_plug: str | None = None
    legacy_root_visibility: bool | None = None
    legacy_root_settable: bool = False
    hidden_fit_joints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RigDisplayPlan:
    operation: str
    value: bool | float
    before: RigDisplayState


def plan_rig_display(before: RigDisplayState, operation: str,
                     value: bool | float) -> RigDisplayPlan:
    if operation not in ("motion", "joints", "axes", "joint_size"):
        raise ValueError("未知的 Display 操作")
    if operation == "joint_size":
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not isfinite(float(value)) or not .01 <= float(value) <= 10):
            raise ValueError("Joint Size 必须在 0.01 到 10 之间")
        value = float(value)
    elif type(value) is not bool:
        raise ValueError("Display 显示开关必须为布尔值")
    if operation == "motion" and before.motion_visibility is None:
        raise ValueError("场景缺少 MotionSystem")
    if operation == "joints" and before.joint_visibility_plug is None:
        raise ValueError("场景缺少可用的关节显示通道")
    if operation == "axes" and not before.joint_axes:
        raise ValueError("DeformationSystem 下没有关节")
    return RigDisplayPlan(operation, value, before)


def audit_rig_display(plan: RigDisplayPlan,
                      after: RigDisplayState) -> tuple[str, ...]:
    before = plan.before
    expected = RigDisplayState(
        motion_visibility=(plan.value if plan.operation == "motion"
                           else before.motion_visibility),
        joint_visibility=(plan.value if plan.operation == "joints"
                          else before.joint_visibility),
        joint_visibility_plug=before.joint_visibility_plug,
        joint_axes=(tuple((path, plan.value) for path, _ in before.joint_axes)
                    if plan.operation == "axes" else before.joint_axes),
        joint_size=(plan.value if plan.operation == "joint_size"
                    else before.joint_size),
        legacy_root_visibility_plug=before.legacy_root_visibility_plug,
        legacy_root_visibility=(
            plan.value if plan.operation == "joints"
            and before.legacy_root_settable else before.legacy_root_visibility),
        legacy_root_settable=before.legacy_root_settable,
        hidden_fit_joints=(
            () if plan.operation == "joints" and plan.value
            else before.hidden_fit_joints),
    )
    if after.joint_visibility_plug != expected.joint_visibility_plug:
        return ("关节显示通道在操作期间改变",)
    if (after.legacy_root_visibility_plug
            != expected.legacy_root_visibility_plug
            or after.legacy_root_settable != expected.legacy_root_settable):
        return ("旧版 root 显示通道在操作期间改变",)
    if tuple(path for path, _ in after.joint_axes) != tuple(
            path for path, _ in expected.joint_axes):
        return ("DeformationSystem 关节集合在操作期间改变",)
    if (after.motion_visibility != expected.motion_visibility
            or after.joint_visibility != expected.joint_visibility
            or after.joint_axes != expected.joint_axes
            or after.legacy_root_visibility != expected.legacy_root_visibility
            or after.hidden_fit_joints != expected.hidden_fit_joints
            or abs(after.joint_size - expected.joint_size) > 1e-6):
        return ("Display 操作后的场景状态不一致",)
    return ()
