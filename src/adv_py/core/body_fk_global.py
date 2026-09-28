"""ADV Fit global/globalTranslate follow for generated FK controls.

The two source blend layers are composed into the existing FK Extra OPM so
registered control DAG paths remain stable. Extra's local animation channels
remain available above the FK curve transform.
"""
from __future__ import annotations

from dataclasses import dataclass

from .body_limb_controls import BodyLimbFkControlSpec
from .fit_metadata import FitJointMetadata


GLOBAL_FOLLOW = "|Group|MotionSystem|GlobalSystem|GlobalFollowMain"


@dataclass(frozen=True, slots=True)
class BodyFkGlobalSpec:
    control: str
    offset: str
    extra: str
    default_weight: float
    translate: bool
    stem: str
    bind_world_matrix: tuple[float, ...]

    @property
    def matrix_name(self) -> str:
        return self.stem + "MM"

    @property
    def rotate_pick_name(self) -> str:
        return self.stem + "PMRot"

    @property
    def rotate_blend_name(self) -> str:
        return self.stem + "BMRot"

    @property
    def rotate_conversion_name(self) -> str:
        return self.stem + "UCRot"

    @property
    def position_pick_name(self) -> str:
        return self.stem + "PMPos"

    @property
    def position_blend_name(self) -> str:
        return self.stem + "BMPos"

    @property
    def position_conversion_name(self) -> str:
        return self.stem + "UCPos"

    @property
    def compose_name(self) -> str:
        return self.stem + "ComposeMM"

    @property
    def node_names(self) -> tuple[str, ...]:
        common = (self.matrix_name, self.rotate_pick_name,
                  self.rotate_blend_name, self.rotate_conversion_name)
        return common + ((self.position_pick_name,
                          self.position_blend_name,
                          self.position_conversion_name,
                          self.compose_name) if self.translate else ())


@dataclass(frozen=True, slots=True)
class BodyFkGlobalState:
    control: str
    extra: str
    extra_parent: str | None
    weight: float | None
    translate_weight: float | None
    weight_range: tuple[float, float] | None
    translate_weight_range: tuple[float, float] | None
    weight_keyable: bool
    translate_weight_keyable: bool | None
    nodes: tuple[tuple[str, str], ...]
    sources: tuple[tuple[str, str | None], ...]
    rotate_pick_flags: tuple[bool, bool, bool, bool] | None
    position_pick_flags: tuple[bool, bool, bool, bool] | None
    conversion_factors: tuple[float, ...]
    bind_world_matrix: tuple[float, ...] | None


def plan_body_fk_global(
    metadata: tuple[FitJointMetadata, ...],
    controls: tuple[BodyLimbFkControlSpec, ...],
) -> tuple[BodyFkGlobalSpec, ...]:
    by_name: dict[str, list[FitJointMetadata]] = {}
    for item in metadata:
        name = item.joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        by_name.setdefault(name, []).append(item)
    result: list[BodyFkGlobalSpec] = []
    names: set[str] = set()
    for control in controls:
        matches = next((by_name[name] for name in control.fit_joint_names
                        if name in by_name), ())
        if len(matches) > 1:
            raise ValueError("Global 来源 Fit 关节短名不唯一："
                             + "／".join(control.fit_joint_names))
        source = matches[0] if matches else None
        if source is None or source.global_weight is None:
            continue
        if (control.extra_path is None
                or control.extra_path.rsplit("|", 1)[0]
                != control.offset_path
                or not 0 <= source.global_weight <= 10):
            raise ValueError("Global 目标缺少有效 FK Extra 层："
                             + control.control_path)
        stem = "AdvPy_Global" + control.control_name
        spec = BodyFkGlobalSpec(
            control.control_path, control.offset_path,
            control.extra_path, float(source.global_weight),
            source.global_translate, stem,
            tuple(value for axis in control.world_axes
                  for value in (*axis, 0.0))
            + (*control.world_position, 1.0))
        if spec.control in names:
            raise ValueError("Global FK 控制重复：" + spec.control)
        names.add(spec.control)
        result.append(spec)
    return tuple(result)


def audit_body_fk_global(
    spec: BodyFkGlobalSpec,
    state: BodyFkGlobalState,
) -> tuple[str, ...]:
    errors: list[str] = []
    if (state.control != spec.control or state.extra != spec.extra
            or state.extra_parent != spec.offset
            or state.weight != spec.default_weight
            or state.translate_weight != (
                spec.default_weight if spec.translate else None)):
        errors.append("Global 控制属性不一致")
    if (state.weight_range != (0.0, 10.0)
            or state.translate_weight_range != (
                (0.0, 10.0) if spec.translate else None)
            or not state.weight_keyable
            or state.translate_weight_keyable != (
                True if spec.translate else None)):
        errors.append("Global 权重通道范围或动画状态不一致")
    expected_types = (
        (spec.matrix_name, "multMatrix"),
        (spec.rotate_pick_name, "pickMatrix"),
        (spec.rotate_blend_name, "blendMatrix"),
        (spec.rotate_conversion_name, "unitConversion"),
    ) + ((
        (spec.position_pick_name, "pickMatrix"),
        (spec.position_blend_name, "blendMatrix"),
        (spec.position_conversion_name, "unitConversion"),
        (spec.compose_name, "multMatrix"),
    ) if spec.translate else ())
    if state.nodes != expected_types:
        errors.append("Global 矩阵节点不一致")
    if (state.bind_world_matrix is None
            or len(state.bind_world_matrix) != 16
            or any(abs(actual - expected) > 1e-4
                   for actual, expected in zip(
                       state.bind_world_matrix, spec.bind_world_matrix))):
        errors.append("Global 绑定世界矩阵不一致")
    expected_sources = body_fk_global_sources(spec)
    if state.sources != expected_sources:
        errors.append("Global 矩阵接线不一致")
    if (state.rotate_pick_flags != (False, True, False, False)
            or state.position_pick_flags != (
                (True, False, False, False) if spec.translate else None)
            or state.conversion_factors != ((0.1, 0.1)
                                            if spec.translate else (0.1,))):
        errors.append("Global 旋转／位移分离参数不一致")
    return tuple(errors)


def body_fk_global_sources(
    spec: BodyFkGlobalSpec,
) -> tuple[tuple[str, str], ...]:
    return (
        (spec.matrix_name + ".matrixIn[1]", GLOBAL_FOLLOW + ".worldMatrix[0]"),
        (spec.matrix_name + ".matrixIn[2]", spec.offset + ".worldInverseMatrix[0]"),
        (spec.rotate_pick_name + ".inputMatrix", spec.matrix_name + ".matrixSum"),
        (spec.rotate_blend_name + ".target[0].targetMatrix",
         spec.rotate_pick_name + ".outputMatrix"),
        (spec.rotate_conversion_name + ".input", spec.control + ".Global"),
        (spec.rotate_blend_name + ".target[0].weight",
         spec.rotate_conversion_name + ".output"),
    ) + ((
        (spec.position_pick_name + ".inputMatrix", spec.matrix_name + ".matrixSum"),
        (spec.position_blend_name + ".target[0].targetMatrix",
         spec.position_pick_name + ".outputMatrix"),
        (spec.position_conversion_name + ".input",
         spec.control + ".GlobalTranslate"),
        (spec.position_blend_name + ".target[0].weight",
         spec.position_conversion_name + ".output"),
        (spec.compose_name + ".matrixIn[0]",
         spec.rotate_blend_name + ".outputMatrix"),
        (spec.compose_name + ".matrixIn[1]",
         spec.position_blend_name + ".outputMatrix"),
        (spec.extra + ".offsetParentMatrix", spec.compose_name + ".matrixSum"),
    ) if spec.translate else (
        (spec.extra + ".offsetParentMatrix",
         spec.rotate_blend_name + ".outputMatrix"),
    ))
