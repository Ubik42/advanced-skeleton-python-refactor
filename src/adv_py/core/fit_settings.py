from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FitSkeletonValidationError(ValueError):
    """Raised when FitSkeleton settings cannot be handled safely."""


class FitSkeletonField(str, Enum):
    VIS_GEOMETRY = "vis_geometry"
    VIS_GEOMETRY_TYPE = "vis_geometry_type"
    VIS_CYLINDERS = "vis_cylinders"
    VIS_BOXES = "vis_boxes"
    VIS_SPHERES = "vis_spheres"
    VIS_BONES = "vis_bones"
    LOCK_CENTER_JOINTS = "lock_center_joints"
    VIS_GAP = "vis_gap"
    VIS_POLE_VECTOR = "vis_pole_vector"
    VIS_JOINT_ORIENT = "vis_joint_orient"
    VIS_JOINT_AXIS = "vis_joint_axis"
    OBJECTS_SKIN = "objects_skin"
    OBJECTS_ALL = "objects_all"
    OBJECTS_RIGHT_EYE = "objects_right_eye"
    OBJECTS_LEFT_EYE = "objects_left_eye"
    GAME_ENGINE = "game_engine"
    USE_OFFSET_PARENT_MATRIX = "use_offset_parent_matrix"
    SUB_CONTROLLERS = "sub_controllers"
    EXTRA_CONTROLLERS = "extra_controllers"
    PRE_REBUILD_SCRIPT = "pre_rebuild_script"
    POST_REBUILD_SCRIPT = "post_rebuild_script"


FitSkeletonValue = bool | int | float | str


_BOOLEAN_FIELDS = frozenset(
    {
        FitSkeletonField.VIS_GEOMETRY,
        FitSkeletonField.VIS_CYLINDERS,
        FitSkeletonField.VIS_BOXES,
        FitSkeletonField.VIS_SPHERES,
        FitSkeletonField.VIS_BONES,
        FitSkeletonField.LOCK_CENTER_JOINTS,
        FitSkeletonField.VIS_POLE_VECTOR,
        FitSkeletonField.VIS_JOINT_ORIENT,
        FitSkeletonField.VIS_JOINT_AXIS,
        FitSkeletonField.GAME_ENGINE,
        FitSkeletonField.USE_OFFSET_PARENT_MATRIX,
        FitSkeletonField.SUB_CONTROLLERS,
        FitSkeletonField.EXTRA_CONTROLLERS,
    }
)
_STRING_FIELDS = frozenset(
    {
        FitSkeletonField.OBJECTS_SKIN,
        FitSkeletonField.OBJECTS_ALL,
        FitSkeletonField.OBJECTS_RIGHT_EYE,
        FitSkeletonField.OBJECTS_LEFT_EYE,
        FitSkeletonField.PRE_REBUILD_SCRIPT,
        FitSkeletonField.POST_REBUILD_SCRIPT,
    }
)
FIT_GEOMETRY_TYPES = ("cylinders", "boxes", "spheres", "bones")


@dataclass(frozen=True, slots=True)
class FitSkeletonSetting:
    field: FitSkeletonField
    value: FitSkeletonValue

    def __post_init__(self) -> None:
        if not isinstance(self.field, FitSkeletonField):
            raise FitSkeletonValidationError("未知的 FitSkeleton 设置字段")
        if self.field in _BOOLEAN_FIELDS and type(self.value) is not bool:
            raise FitSkeletonValidationError(f"{self.field.value} 必须是布尔值")
        if self.field in _STRING_FIELDS and not isinstance(self.value, str):
            raise FitSkeletonValidationError(f"{self.field.value} 必须是字符串")
        if self.field is FitSkeletonField.VIS_GAP and (
            isinstance(self.value, bool) or not isinstance(self.value, (int, float))
        ):
            raise FitSkeletonValidationError("vis_gap 必须是数值")
        if self.field is FitSkeletonField.VIS_GEOMETRY_TYPE and not isinstance(
            self.value, str
        ):
            raise FitSkeletonValidationError("vis_geometry_type 必须是字符串")


@dataclass(frozen=True, slots=True)
class FitSkeletonSettings:
    container: str
    settings: tuple[FitSkeletonSetting, ...]

    def __post_init__(self) -> None:
        if not self.container:
            raise FitSkeletonValidationError("FitSkeleton 容器路径不能为空")
        fields = tuple(item.field for item in self.settings)
        if len(fields) != len(set(fields)):
            raise FitSkeletonValidationError("FitSkeleton 设置包含重复字段")

    @property
    def present_fields(self) -> frozenset[FitSkeletonField]:
        return frozenset(item.field for item in self.settings)

    def value(self, field: FitSkeletonField) -> FitSkeletonValue | None:
        for item in self.settings:
            if item.field is field:
                return item.value
        return None


@dataclass(frozen=True, slots=True)
class FitSkeletonIssue:
    code: str
    message: str
    field: FitSkeletonField | None = None


def default_fit_skeleton_settings(
    container: str,
    *,
    vis_gap: float = 0.75,
) -> FitSkeletonSettings:
    values: dict[FitSkeletonField, FitSkeletonValue] = {
        field: False for field in _BOOLEAN_FIELDS
    }
    values[FitSkeletonField.LOCK_CENTER_JOINTS] = True
    values[FitSkeletonField.VIS_GEOMETRY_TYPE] = FIT_GEOMETRY_TYPES[0]
    values[FitSkeletonField.VIS_GAP] = vis_gap
    values.update({field: "" for field in _STRING_FIELDS})
    settings = tuple(
        FitSkeletonSetting(field, values[field]) for field in FitSkeletonField
    )
    defaults = FitSkeletonSettings(container=container, settings=settings)
    issues = audit_fit_skeleton_settings(defaults, require_complete=True)
    if issues:
        raise FitSkeletonValidationError(issues[0].message)
    return defaults


def audit_fit_skeleton_settings(
    settings: FitSkeletonSettings,
    *,
    require_complete: bool = True,
) -> tuple[FitSkeletonIssue, ...]:
    issues: list[FitSkeletonIssue] = []
    if require_complete:
        for field in FitSkeletonField:
            if field not in settings.present_fields:
                issues.append(
                    FitSkeletonIssue(
                        "missing_field",
                        f"FitSkeleton 缺少设置：{field.value}",
                        field,
                    )
                )

    geometry_type = settings.value(FitSkeletonField.VIS_GEOMETRY_TYPE)
    if geometry_type is not None and geometry_type not in FIT_GEOMETRY_TYPES:
        issues.append(
            FitSkeletonIssue(
                "invalid_geometry_type",
                f"不支持的 FitSkeleton 几何显示类型：{geometry_type}",
                FitSkeletonField.VIS_GEOMETRY_TYPE,
            )
        )

    vis_gap = settings.value(FitSkeletonField.VIS_GAP)
    if vis_gap is not None and not 0.0 <= float(vis_gap) <= 1.0:
        issues.append(
            FitSkeletonIssue(
                "vis_gap_out_of_range",
                "FitSkeleton 显示间距必须位于 0 到 1",
                FitSkeletonField.VIS_GAP,
            )
        )
    return tuple(issues)
