from __future__ import annotations

from dataclasses import dataclass

from .body_arm_blend import BodyArmBlendPlan
from .body_arm_ik import BodyArmIkPlan
from .body_controls import BodyArmFkControlPlan
from .fit_symmetry import FitBuildSide


@dataclass(frozen=True, slots=True)
class BodyArmVisibilitySideSpec:
    side: FitBuildSide
    blend_plug: str
    reverse_output_plug: str
    fk_offset_path: str
    ik_offset_paths: tuple[str, str]


@dataclass(frozen=True, slots=True)
class BodyArmVisibilityPlan:
    sides: tuple[BodyArmVisibilitySideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyArmVisibilitySideState:
    side: FitBuildSide
    fk_visibility_source: str | None
    ik_visibility_sources: tuple[str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyArmVisibilitySnapshot:
    sides: tuple[BodyArmVisibilitySideState, ...]


@dataclass(frozen=True, slots=True)
class BodyArmVisibilityIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_arm_visibility(
    fk_controls: BodyArmFkControlPlan,
    ik: BodyArmIkPlan,
    blend: BodyArmBlendPlan,
) -> BodyArmVisibilityPlan:
    sides = []
    for blend_side in blend.sides:
        fk_roots = tuple(
            control.offset_path
            for control in fk_controls.controls
            if control.side is blend_side.side
            and control.parent_path == fk_controls.root_path
        )
        ik_limbs = tuple(limb for limb in ik.limbs if limb.side is blend_side.side)
        if len(fk_roots) != 1 or len(ik_limbs) != 1:
            raise ValueError("Arm 显隐计划要求每侧唯一的 FK 根控制和 IK 控制组")
        limb = ik_limbs[0]
        sides.append(
            BodyArmVisibilitySideSpec(
                blend_side.side,
                f"{blend.settings_path}.{blend_side.attribute}",
                f"{blend_side.reverse_name}.outputX",
                fk_roots[0],
                (limb.wrist_offset_path, limb.pole_offset_path),
            )
        )
    return BodyArmVisibilityPlan(tuple(sides))


def audit_body_arm_visibility(
    plan: BodyArmVisibilityPlan,
    snapshot: BodyArmVisibilitySnapshot,
) -> tuple[BodyArmVisibilityIssue, ...]:
    issues = []
    actual = {state.side: state for state in snapshot.sides}
    for spec in plan.sides:
        state = actual.get(spec.side)
        if state is None:
            issues.append(BodyArmVisibilityIssue("missing_side", "缺少 Arm 控制显隐侧", spec.side.value))
            continue
        if state.fk_visibility_source != spec.reverse_output_plug:
            issues.append(BodyArmVisibilityIssue("fk_visibility_wiring", "FK 控制显隐连线不一致", spec.side.value))
        if state.ik_visibility_sources != (spec.blend_plug, spec.blend_plug):
            issues.append(BodyArmVisibilityIssue("ik_visibility_wiring", "IK/PV 控制显隐连线不一致", spec.side.value))
    return tuple(issues)
