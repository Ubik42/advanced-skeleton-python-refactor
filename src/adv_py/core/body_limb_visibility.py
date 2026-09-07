from __future__ import annotations

from dataclasses import dataclass

from .body_limb_blend import BodyLimbBlendPlan
from .body_limb_controls import BodyLimbFkControlPlan
from .fit_symmetry import FitBuildSide


@dataclass(frozen=True, slots=True)
class BodyLimbVisibilitySideSpec:
    side: FitBuildSide
    blend_plug: str
    reverse_output_plug: str
    fk_offset_path: str
    ik_offset_paths: tuple[str, str]


@dataclass(frozen=True, slots=True)
class BodyLimbVisibilityPlan:
    sides: tuple[BodyLimbVisibilitySideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbVisibilitySideState:
    side: FitBuildSide
    fk_visibility_source: str | None
    ik_visibility_sources: tuple[str | None, str | None]


@dataclass(frozen=True, slots=True)
class BodyLimbVisibilitySnapshot:
    sides: tuple[BodyLimbVisibilitySideState, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbVisibilityInputState:
    existing_source_plugs: tuple[str, ...]
    writable_target_plugs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbVisibilityIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_limb_visibility(
    fk_controls: BodyLimbFkControlPlan,
    blend: BodyLimbBlendPlan,
    ik_offsets_by_side: dict[FitBuildSide, tuple[str, str]],
    *,
    limb_label: str,
) -> BodyLimbVisibilityPlan:
    sides = []
    for blend_side in blend.sides:
        fk_roots = tuple(
            control.offset_path
            for control in fk_controls.controls
            if control.side is blend_side.side
            and control.parent_path == fk_controls.root_path
        )
        ik_offsets = ik_offsets_by_side.get(blend_side.side)
        if len(fk_roots) != 1 or ik_offsets is None or len(ik_offsets) != 2:
            raise ValueError(
                f"{limb_label} 显隐计划要求每侧唯一的 FK 根控制和两个 IK 控制组"
            )
        sides.append(BodyLimbVisibilitySideSpec(
            blend_side.side,
            f"{blend.settings_path}.{blend_side.attribute}",
            f"{blend_side.reverse_name}.outputX",
            fk_roots[0],
            ik_offsets,
        ))
    return BodyLimbVisibilityPlan(tuple(sides))


def audit_body_limb_visibility_input(
    plan: BodyLimbVisibilityPlan,
    state: BodyLimbVisibilityInputState,
    *,
    limb_label: str,
) -> tuple[BodyLimbVisibilityIssue, ...]:
    sources = set(state.existing_source_plugs)
    targets = set(state.writable_target_plugs)
    issues = []
    for side in plan.sides:
        for plug in (side.reverse_output_plug, side.blend_plug):
            if plug not in sources:
                issues.append(BodyLimbVisibilityIssue(
                    "missing_source", f"{limb_label} 显隐源属性不存在", plug
                ))
        for path in (side.fk_offset_path, *side.ik_offset_paths):
            plug = f"{path}.visibility"
            if plug not in targets:
                issues.append(BodyLimbVisibilityIssue(
                    "unwritable_target", f"{limb_label} 显隐目标不可写或已有输入", plug
                ))
    return tuple(issues)


def audit_body_limb_visibility(
    plan: BodyLimbVisibilityPlan,
    snapshot: BodyLimbVisibilitySnapshot,
    *,
    limb_label: str,
) -> tuple[BodyLimbVisibilityIssue, ...]:
    issues = []
    actual = {state.side: state for state in snapshot.sides}
    for spec in plan.sides:
        state = actual.get(spec.side)
        if state is None:
            issues.append(BodyLimbVisibilityIssue(
                "missing_side", f"缺少 {limb_label} 控制显隐侧", spec.side.value
            ))
            continue
        if state.fk_visibility_source != spec.reverse_output_plug:
            issues.append(BodyLimbVisibilityIssue(
                "fk_visibility_wiring", "FK 控制显隐连线不一致", spec.side.value
            ))
        if state.ik_visibility_sources != (spec.blend_plug, spec.blend_plug):
            issues.append(BodyLimbVisibilityIssue(
                "ik_visibility_wiring", "IK/PV 控制显隐连线不一致", spec.side.value
            ))
    return tuple(issues)
