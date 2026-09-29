from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re
from math import isfinite


class FitJointValidationError(ValueError):
    """Raised when Fit joint input cannot be resolved safely."""


class FitJointField(str, Enum):
    TWIST_JOINTS = "twist_joints"
    BENDY_CONTROLS = "bendy_controls"
    INBETWEEN_JOINTS = "inbetween_joints"
    UNTWISTER = "untwister"
    CONTROL = "control"
    TWEAKER_CONTROL = "tweaker_control"
    NO_CONTROL = "no_control"
    NO_SKIN = "no_skin"
    SEG_SCALE_COMP = "seg_scale_comp"
    HIP_SWINGER = "hip_swinger"
    COG = "cog"
    AIM = "aim"
    FOOT_PIVOTS = "foot_pivots"
    NO_MIRROR = "no_mirror"
    NO_MIRROR_LEFT = "no_mirror_left"
    NO_FLIP = "no_flip"
    CHILD_OF_PART = "child_of_part"
    GLOBAL_WEIGHT = "global_weight"
    GLOBAL_TRANSLATE = "global_translate"
    WORLD_ORIENT_UP = "world_orient_up"
    WORLD_ORIENT_FORWARD = "world_orient_forward"
    IK_LOCAL_MODE = "ik_local_mode"
    PARENT_CONSTRAINT = "parent_constraint"
    POINT_CONSTRAINT = "point_constraint"
    ORIENT_CONSTRAINT = "orient_constraint"
    SCALE_CONSTRAINT = "scale_constraint"
    FOLLOW = "follow"
    FOLLOW_LEFT_RIGHT = "follow_left_right"
    FOLLOW_WORLD = "follow_world"
    FOLLOW_BY_NAME = "follow_by_name"
    FOLLOW_SPACES = "follow_spaces"
    IK_FOLLOW = "ik_follow"


FitJointValue = bool | int | float | str | tuple[tuple[str, float], ...]


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
    control: bool = False
    tweaker_control: bool = False
    no_control: bool = False
    no_skin: bool = False
    seg_scale_comp: bool | None = None
    hip_swinger: bool | None = None
    no_mirror: bool = False
    no_mirror_left: bool = False
    no_flip: bool = False
    inherited_no_flip: bool = False
    local_no_flip: bool | None = None
    child_of_part: int | None = None
    global_weight: float | None = None
    global_translate: bool = False
    world_orient_up: str | None = None
    world_orient_forward: str | None = None
    ik_local_mode: str | None = None
    present_fields: frozenset[FitJointField] = frozenset()
    cog: bool = False
    aim: bool = False
    foot_pivots: bool = False
    parent_constraint: str | None = None
    point_constraint: str | None = None
    orient_constraint: str | None = None
    scale_constraint: str | None = None
    follow: str | None = None
    follow_left_right: bool = False
    follow_world: bool = False
    follow_by_name: tuple[tuple[str, float], ...] = ()
    follow_spaces: bool = False
    ik_follow: str | None = None


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
    FitJointField.CONTROL,
    FitJointField.TWEAKER_CONTROL,
    FitJointField.NO_CONTROL,
    FitJointField.NO_SKIN,
    FitJointField.SEG_SCALE_COMP,
    FitJointField.HIP_SWINGER,
    FitJointField.COG,
    FitJointField.AIM,
    FitJointField.FOOT_PIVOTS,
    FitJointField.NO_MIRROR,
    FitJointField.NO_MIRROR_LEFT,
    FitJointField.NO_FLIP,
    FitJointField.GLOBAL_TRANSLATE,
    FitJointField.FOLLOW_LEFT_RIGHT,
    FitJointField.FOLLOW_WORLD,
    FitJointField.FOLLOW_SPACES,
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
_CONSTRAINT_FIELDS = frozenset((
    FitJointField.PARENT_CONSTRAINT, FitJointField.POINT_CONSTRAINT,
    FitJointField.ORIENT_CONSTRAINT, FitJointField.SCALE_CONSTRAINT,
))
_TARGET_FIELDS = _CONSTRAINT_FIELDS | {
    FitJointField.FOLLOW, FitJointField.IK_FOLLOW}
_BUILD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_FOLLOW_RESERVED = frozenset(("LeftRight", "World", "Spaces"))


def validate_follow_by_name(value: object) -> None:
    if not isinstance(value, tuple):
        raise FitJointValidationError("follow_by_name 必须是目标与权重的有序列表")
    names: set[str] = set()
    for entry in value:
        if (not isinstance(entry, tuple) or len(entry) != 2
                or not isinstance(entry[0], str)
                or not _BUILD_NAME.fullmatch(entry[0])
                or entry[0] in _FOLLOW_RESERVED):
            raise FitJointValidationError("Follow* 目标名称无效")
        name, weight = entry
        if name in names:
            raise FitJointValidationError("Follow* 目标名称重复：" + name)
        names.add(name)
        if (isinstance(weight, bool) or not isinstance(weight, (int, float))
                or not isfinite(weight) or weight < 0 or weight > 10):
            raise FitJointValidationError("Follow* 权重必须在 0–10 之间")


def validate_fit_joint_value(
    field: FitJointField, value: FitJointValue | None
) -> None:
    if value is None:
        return
    if field is FitJointField.FOLLOW_BY_NAME:
        validate_follow_by_name(value)
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
    if field in _TARGET_FIELDS and (
            not isinstance(value, str) or not _BUILD_NAME.fullmatch(value)):
        raise FitJointValidationError(
            f"{field.value} 必须是未带侧别的关节名称")


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
        if edit.field is FitJointField.FOLLOW_BY_NAME and edit.value is None:
            values["follow_by_name"] = ()
            present.discard(edit.field)
            continue
        if edit.field is FitJointField.FOLLOW and edit.value is None:
            values["follow_left_right"] = False
            values["follow_world"] = False
            present.discard(FitJointField.FOLLOW_LEFT_RIGHT)
            present.discard(FitJointField.FOLLOW_WORLD)
        if edit.field is FitJointField.NO_FLIP:
            values["local_no_flip"] = edit.value
            values["no_flip"] = (
                metadata.inherited_no_flip or bool(edit.value)
            )
            if edit.value is None:
                present.discard(edit.field)
            else:
                present.add(edit.field)
            continue
        if edit.value is None or (edit.field is FitJointField.AIM
                                  and edit.value is False):
            present.discard(edit.field)
            values[edit.field.value] = (
                False if (edit.field in _BOOLEAN_FIELDS
                          and edit.field not in (
                              FitJointField.HIP_SWINGER,
                              FitJointField.SEG_SCALE_COMP))
                else None
            )
        else:
            present.add(edit.field)
            values[edit.field.value] = edit.value
    values["present_fields"] = frozenset(present)
    return replace(metadata, **values)


def audit_fit_joint(metadata: FitJointMetadata) -> tuple[FitJointIssue, ...]:
    issues: list[FitJointIssue] = []
    try:
        validate_follow_by_name(metadata.follow_by_name)
    except FitJointValidationError as error:
        issues.append(FitJointIssue(
            metadata.joint, "invalid_follow_by_name", str(error)))
    if type(metadata.cog) is not bool:
        issues.append(FitJointIssue(
            metadata.joint, "invalid_cog", "COG 开关必须是布尔值"))
    if type(metadata.aim) is not bool:
        issues.append(FitJointIssue(
            metadata.joint, "invalid_aim", "Aim 标记必须是布尔值"))
    if type(metadata.control) is not bool:
        issues.append(FitJointIssue(
            metadata.joint, "invalid_control", "Control 开关必须是布尔值"))
    if type(metadata.tweaker_control) is not bool:
        issues.append(FitJointIssue(
            metadata.joint, "invalid_tweaker_control",
            "Tweaker Control 开关必须是布尔值"))
    if type(metadata.no_control) is not bool:
        issues.append(FitJointIssue(
            metadata.joint, "invalid_no_control", "No Control 开关必须是布尔值"))
    if type(metadata.no_skin) is not bool:
        issues.append(FitJointIssue(
            metadata.joint, "invalid_no_skin", "No Skin 开关必须是布尔值"))
    if (metadata.seg_scale_comp is not None
            and type(metadata.seg_scale_comp) is not bool):
        issues.append(FitJointIssue(
            metadata.joint, "invalid_seg_scale_comp",
            "Segment Scale Compensate 必须是布尔值"))
    if type(metadata.foot_pivots) is not bool:
        issues.append(FitJointIssue(
            metadata.joint, "invalid_foot_pivots", "Foot Pivots 开关必须是布尔值"))
    if type(metadata.follow_spaces) is not bool:
        issues.append(FitJointIssue(
            metadata.joint, "invalid_follow_spaces",
            "Follow Spaces 开关必须是布尔值"))
    for field in _TARGET_FIELDS:
        value = getattr(metadata, field.value)
        if value is not None and (not isinstance(value, str)
                                  or not _BUILD_NAME.fullmatch(value)):
            issues.append(FitJointIssue(
                metadata.joint, "invalid_" + field.value,
                field.value + " 目标关节名称无效"))
    if (metadata.follow_left_right or metadata.follow_world) and not metadata.follow:
        issues.append(FitJointIssue(
            metadata.joint, "follow_options_without_target",
            "Follow 左右／世界选项需要 Follow 目标关节"))
    if (metadata.follow_spaces and any(
            name in {"Main", "Root", "Chest", "Parent"}
            for name, _ in metadata.follow_by_name)):
        issues.append(FitJointIssue(
            metadata.joint, "follow_space_name_conflict",
            "Follow* 命名目标与 Follow Spaces 权重属性冲突"))

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
    if metadata.untwister and not metadata.inbetween_joints:
        issues.append(
            FitJointIssue(
                metadata.joint,
                "untwister_without_inbetween",
                "UnTwister 设置需要至少一段 Inbetween 关节",
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
