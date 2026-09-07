from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class FitJointValidationError(ValueError):
    """Raised when Fit joint input cannot be resolved safely."""


class FitJointField(str, Enum):
    TWIST_JOINTS = "twist_joints"
    BENDY_CONTROLS = "bendy_controls"
    INBETWEEN_JOINTS = "inbetween_joints"
    UNTWISTER = "untwister"
    NO_MIRROR = "no_mirror"
    NO_MIRROR_LEFT = "no_mirror_left"
    CHILD_OF_PART = "child_of_part"
    GLOBAL_WEIGHT = "global_weight"
    GLOBAL_TRANSLATE = "global_translate"
    WORLD_ORIENT_UP = "world_orient_up"
    WORLD_ORIENT_FORWARD = "world_orient_forward"
    IK_LOCAL_MODE = "ik_local_mode"


FitJointValue = bool | int | float | str


@dataclass(frozen=True, slots=True)
class FitJointFieldEdit:
    field: FitJointField
    value: FitJointValue | None


@dataclass(frozen=True, slots=True)
class FitJointPatch:
    edits: tuple[FitJointFieldEdit, ...]

    @classmethod
    def from_values(cls, **values: FitJointValue | None) -> "FitJointPatch":
        if not values:
            raise FitJointValidationError("Fit joint 变更不能为空")
        edits: list[FitJointFieldEdit] = []
        for name, value in values.items():
            try:
                field = FitJointField(name)
            except ValueError as error:
                raise FitJointValidationError(f"未知 Fit joint 字段：{name}") from error
            edits.append(FitJointFieldEdit(field=field, value=value))
        return cls(edits=tuple(edits))

    def __post_init__(self) -> None:
        if not self.edits:
            raise FitJointValidationError("Fit joint 变更不能为空")
        fields = tuple(edit.field for edit in self.edits)
        if len(fields) != len(set(fields)):
            raise FitJointValidationError("Fit joint 变更不能包含重复字段")
        for edit in self.edits:
            validate_fit_joint_value(edit.field, edit.value)


@dataclass(frozen=True, slots=True)
class FitJointMetadata:
    """Portable values that affect how one fit joint is interpreted."""

    joint: str
    twist_joints: int | None = None
    bendy_controls: int | None = None
    inbetween_joints: int | None = None
    untwister: bool = False
    no_mirror: bool = False
    no_mirror_left: bool = False
    child_of_part: int | None = None
    global_weight: float | None = None
    global_translate: bool = False
    world_orient_up: str | None = None
    world_orient_forward: str | None = None
    ik_local_mode: str | None = None
    present_fields: frozenset[FitJointField] = frozenset()


@dataclass(frozen=True, slots=True)
class FitJointIssue:
    joint: str
    code: str
    message: str


_INTEGER_FIELDS = {
    FitJointField.TWIST_JOINTS,
    FitJointField.BENDY_CONTROLS,
    FitJointField.INBETWEEN_JOINTS,
    FitJointField.CHILD_OF_PART,
}
_BOOLEAN_FIELDS = {
    FitJointField.UNTWISTER,
    FitJointField.NO_MIRROR,
    FitJointField.NO_MIRROR_LEFT,
    FitJointField.GLOBAL_TRANSLATE,
}
_ENUM_OPTIONS = {
    FitJointField.WORLD_ORIENT_UP: {
        "xUp",
        "yUp",
        "zUp",
        "xDown",
        "yDown",
        "zDown",
    },
    FitJointField.WORLD_ORIENT_FORWARD: {
        "xForward",
        "yForward",
        "zForward",
        "xBackward",
        "yBackward",
        "zBackward",
        "free",
    },
    FitJointField.IK_LOCAL_MODE: {"addCtrl", "nonZero", "localOrient"},
}


def validate_fit_joint_value(
    field: FitJointField, value: FitJointValue | None
) -> None:
    if value is None:
        return
    if field in _INTEGER_FIELDS and type(value) is not int:
        raise FitJointValidationError(f"{field.value} 必须是整数")
    if field in _BOOLEAN_FIELDS and type(value) is not bool:
        raise FitJointValidationError(f"{field.value} 必须是布尔值")
    if field is FitJointField.GLOBAL_WEIGHT and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise FitJointValidationError("global_weight 必须是数值")
    if field in _ENUM_OPTIONS and value not in _ENUM_OPTIONS[field]:
        options = "、".join(sorted(_ENUM_OPTIONS[field]))
        raise FitJointValidationError(f"{field.value} 必须是以下值之一：{options}")


def fit_joint_value(
    metadata: FitJointMetadata, field: FitJointField
) -> FitJointValue | None:
    return getattr(metadata, field.value)


def predict_fit_joint_metadata(
    metadata: FitJointMetadata, patch: FitJointPatch
) -> FitJointMetadata:
    values: dict[str, object] = {}
    present = set(metadata.present_fields)
    for edit in patch.edits:
        if edit.value is None:
            present.discard(edit.field)
            values[edit.field.value] = (
                False if edit.field in _BOOLEAN_FIELDS else None
            )
        else:
            present.add(edit.field)
            values[edit.field.value] = edit.value
    values["present_fields"] = frozenset(present)
    return replace(metadata, **values)


def audit_fit_joint(metadata: FitJointMetadata) -> tuple[FitJointIssue, ...]:
    issues: list[FitJointIssue] = []

    for field_name, value, label in (
        ("twist_joints", metadata.twist_joints, "Twist 关节数量"),
        ("bendy_controls", metadata.bendy_controls, "Bendy 控制器数量"),
        ("inbetween_joints", metadata.inbetween_joints, "Inbetween 关节数量"),
    ):
        if value is not None and value < 0:
            issues.append(
                FitJointIssue(
                    metadata.joint,
                    f"negative_{field_name}",
                    f"{label}不能小于 0",
                )
            )

    if metadata.twist_joints is not None and metadata.inbetween_joints is not None:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "mixed_subdivision_modes",
                "同一 Fit joint 不能同时启用 Twist 与 Inbetween",
            )
        )
    if metadata.bendy_controls is not None and metadata.twist_joints is None:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "bendy_without_twist",
                "Bendy 控制器设置需要 Twist 模式",
            )
        )
    if metadata.untwister and metadata.inbetween_joints is None:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "untwister_without_inbetween",
                "UnTwister 设置需要 Inbetween 模式",
            )
        )
    if metadata.no_mirror_left and not metadata.no_mirror:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "left_rule_without_no_mirror",
                "noMirrorLeft 需要同时启用 noMirror",
            )
        )
    if metadata.child_of_part is not None and not 1 <= metadata.child_of_part <= 10:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "child_of_part_out_of_range",
                "childOfPart 必须位于 1 到 10",
            )
        )
    if metadata.global_weight is not None and not 0.0 <= metadata.global_weight <= 10.0:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "global_weight_out_of_range",
                "global 权重必须位于 0 到 10",
            )
        )
    return tuple(issues)
