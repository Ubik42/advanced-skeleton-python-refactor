from __future__ import annotations

from dataclasses import dataclass

from .body_limb_mechanisms import BodyLimbMechanismPlan, BodyLimbMechanismRole
from .body_skeleton import BodySkeletonSnapshot
from .fit_symmetry import FitBuildSide


class BodyLimbBlendValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BodyLimbBlendJointSpec:
    body_joint: str
    fk_driver: str
    ik_driver: str
    constraint_name: str
    translation_constraint_name: str | None


@dataclass(frozen=True, slots=True)
class BodyLimbBlendSideSpec:
    side: FitBuildSide
    attribute: str
    reverse_name: str
    joints: tuple[BodyLimbBlendJointSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbBlendPlan:
    settings_path: str
    settings_name: str
    sides: tuple[BodyLimbBlendSideSpec, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbBlendJointState:
    constraint_name: str
    body_joint: str | None
    targets: tuple[str, ...]
    fk_weight_source: str | None
    ik_weight_source: str | None
    translation_constraint_name: str | None
    translation_targets: tuple[str, ...]
    translation_fk_weight_source: str | None
    translation_ik_weight_source: str | None
    translation_driven_joint: str | None


@dataclass(frozen=True, slots=True)
class BodyLimbBlendSideState:
    side: FitBuildSide
    attribute_plug: str
    attribute_value: float
    reverse_name: str
    reverse_input_source: str | None
    joints: tuple[BodyLimbBlendJointState, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbBlendSnapshot:
    settings_path: str
    sides: tuple[BodyLimbBlendSideState, ...]


@dataclass(frozen=True, slots=True)
class BodyLimbBlendIssue:
    code: str
    message: str
    subject: str | None = None


def plan_body_limb_blend(
    body: BodySkeletonSnapshot,
    mechanisms: BodyLimbMechanismPlan,
    *,
    limb_label: str,
    joint_names: tuple[str, str, str],
    translated_joint_names: tuple[str, ...],
) -> BodyLimbBlendPlan:
    if (
        not limb_label.isalpha()
        or len(joint_names) != 3
        or len(set(joint_names)) != 3
        or any(not name.isalpha() for name in joint_names)
        or not set(translated_joint_names).issubset(joint_names)
    ):
        raise BodyLimbBlendValidationError("Limb IK/FK blend 定义无效")
    body_by_name = {joint.name: joint.path for joint in body.joints}
    required = tuple(
        f"{part}_{suffix}"
        for suffix in ("R", "L")
        for part in joint_names
    )
    if len(body_by_name) != len(body.joints) or any(
        name not in body_by_name for name in required
    ):
        raise BodyLimbBlendValidationError(
            f"Body 缺少唯一的双侧 {limb_label} 三关节链"
        )
    drivers = {
        (spec.source_joint, spec.role): spec.path
        for spec in mechanisms.joints
    }

    sides = []
    token = limb_label[0].lower() + limb_label[1:]
    for suffix, side in (("R", FitBuildSide.RIGHT), ("L", FitBuildSide.LEFT)):
        joints = []
        for part in joint_names:
            body_path = body_by_name[f"{part}_{suffix}"]
            try:
                fk = drivers[(body_path, BodyLimbMechanismRole.FK)]
                ik = drivers[(body_path, BodyLimbMechanismRole.IK)]
            except KeyError as exc:
                raise BodyLimbBlendValidationError(
                    f"{limb_label} mechanism 缺少 FK/IK driver"
                ) from exc
            joints.append(BodyLimbBlendJointSpec(
                body_joint=body_path,
                fk_driver=fk,
                ik_driver=ik,
                constraint_name=f"AdvPy_{part}IKFKBlend_{suffix}",
                translation_constraint_name=(
                    f"AdvPy_{part}IKFKTranslate_{suffix}"
                    if part in translated_joint_names
                    else None
                ),
            ))
        sides.append(BodyLimbBlendSideSpec(
            side=side,
            attribute=f"{token}IkFk_{suffix}",
            reverse_name=f"AdvPy_{limb_label}IKFKReverse_{suffix}",
            joints=tuple(joints),
        ))
    settings_name = f"AdvPy_{limb_label}Settings"
    return BodyLimbBlendPlan(
        f"|{settings_name}",
        settings_name,
        tuple(sides),
    )


def audit_body_limb_blend(
    plan: BodyLimbBlendPlan,
    snapshot: BodyLimbBlendSnapshot,
    *,
    limb_label: str,
    expected_attribute_value: float | None = 0.0,
) -> tuple[BodyLimbBlendIssue, ...]:
    issues = []
    if snapshot.settings_path != plan.settings_path:
        issues.append(BodyLimbBlendIssue(
            "settings_mismatch", f"{limb_label} IK/FK 设置节点不一致"
        ))
    actual_sides = {state.side: state for state in snapshot.sides}
    for spec in plan.sides:
        state = actual_sides.get(spec.side)
        if state is None:
            issues.append(BodyLimbBlendIssue(
                "missing_side", f"缺少 {limb_label} IK/FK 侧", spec.side.value
            ))
            continue
        plug = f"{plan.settings_path}.{spec.attribute}"
        value_mismatch = (
            expected_attribute_value is not None
            and abs(state.attribute_value - expected_attribute_value) > 1e-6
        )
        if (
            state.attribute_plug != plug
            or value_mismatch
            or state.reverse_name != spec.reverse_name
            or state.reverse_input_source != plug
        ):
            issues.append(BodyLimbBlendIssue(
                "blend_driver_mismatch",
                f"{limb_label} IK/FK 属性或 reverse 连线不一致",
                spec.side.value,
            ))
        expected = {joint.constraint_name: joint for joint in spec.joints}
        actual = {joint.constraint_name: joint for joint in state.joints}
        if set(expected) != set(actual):
            issues.append(BodyLimbBlendIssue(
                "constraint_set_mismatch",
                f"{limb_label} IK/FK 约束集合不一致",
                spec.side.value,
            ))
            continue
        for name, wanted in expected.items():
            current = actual[name]
            if (
                current.body_joint != wanted.body_joint
                or current.targets != (wanted.fk_driver, wanted.ik_driver)
                or current.fk_weight_source != f"{spec.reverse_name}.outputX"
                or current.ik_weight_source != plug
            ):
                issues.append(BodyLimbBlendIssue(
                    "constraint_wiring_mismatch",
                    f"{limb_label} IK/FK 双源权重连线不一致",
                    name,
                ))
            if wanted.translation_constraint_name is None:
                if (
                    current.translation_constraint_name is not None
                    or current.translation_targets
                ):
                    issues.append(BodyLimbBlendIssue(
                        "unexpected_translation_blend",
                        f"{limb_label} proximal joint 存在计划外位移 blend",
                        name,
                    ))
            elif (
                current.translation_constraint_name
                != wanted.translation_constraint_name
                or current.translation_targets
                != (wanted.fk_driver, wanted.ik_driver)
                or current.translation_fk_weight_source
                != f"{spec.reverse_name}.outputX"
                or current.translation_ik_weight_source != plug
                or current.translation_driven_joint != wanted.body_joint
            ):
                issues.append(BodyLimbBlendIssue(
                    "translation_wiring_mismatch",
                    f"{limb_label} FK/IK 位移权重连线不一致",
                    wanted.translation_constraint_name,
                ))
    return tuple(issues)
