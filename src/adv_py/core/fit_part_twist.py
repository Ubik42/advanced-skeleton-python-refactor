"""Host-independent twist distribution for Fit Part chains."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_part import FitPartJointSpec


class FitPartTwistValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FitPartTwistSource:
    start_body: str
    down_twist_plug: str
    up_twist_plug: str | None = None
    subtract_body_twist: bool = True

    def __post_init__(self) -> None:
        if not self.start_body or not self.down_twist_plug:
            raise FitPartTwistValidationError("Part 扭转来源不能为空")
        if not isinstance(self.subtract_body_twist, bool):
            raise FitPartTwistValidationError("Body 扭转补偿开关必须是布尔值")


@dataclass(frozen=True, slots=True)
class FitPartRotationInput:
    start_body: str
    rotation_plug: str
    rotate_order_plug: str
    up_twist_plug: str | None = None
    ik_rotation_plug: str | None = None
    ik_rotate_order_plug: str | None = None
    ik_fk_blend_plug: str | None = None
    subtract_body_twist: bool = True


@dataclass(frozen=True, slots=True)
class FitPartTwistProjection:
    input: FitPartRotationInput
    compose_name: str
    decompose_name: str
    project_name: str
    ik_compose_name: str | None = None
    ik_decompose_name: str | None = None
    ik_project_name: str | None = None
    blend_name: str | None = None

    @property
    def output_plug(self) -> str:
        if self.blend_name:
            return self.blend_name + ".output"
        return self.project_name + ".outputRotateX"

    def source(self) -> FitPartTwistSource:
        return FitPartTwistSource(
            self.input.start_body, self.output_plug,
            self.input.up_twist_plug,
            self.input.subtract_body_twist,
        )


def plan_standard_fit_part_rotation_inputs(
    parts: tuple[FitPartJointSpec, ...],
) -> tuple[FitPartRotationInput, ...]:
    """Resolve the established Arm/Leg rig channels for standard Fit chains."""
    starts = {part.start_body: part for part in parts}
    result = []
    for start, part in starts.items():
        stem = part.start_body_name.rsplit("_", 1)[0]
        side = part.side.value
        if stem in ("Shoulder", "Elbow"):
            up = (f"AdvPy_LowerArmTwistProject_{side}.outputRotateX"
                  if stem == "Elbow" else None)
            result.append(FitPartRotationInput(
                start, start + ".rotate", start + ".rotateOrder", up))
        elif stem == "Hip":
            fk = f"AdvPy_HipFKDriver_{side}"
            ik = f"AdvPy_HipIKDriver_{side}"
            result.append(FitPartRotationInput(
                start, fk + ".rotate", fk + ".rotateOrder",
                f"AdvPy_UpperLegTwistProject_{side}.outputRotateX",
                ik + ".rotate", ik + ".rotateOrder",
                f"AdvPy_LegSettings.legIkFk_{side}"))
        else:
            raise FitPartTwistValidationError(
                "标准扭转来源未定义，需显式提供：" + part.start_body_name)
    return tuple(result)


def plan_fit_part_twist_projections(
    inputs: tuple[FitPartRotationInput, ...],
) -> tuple[FitPartTwistProjection, ...]:
    if len({item.start_body for item in inputs}) != len(inputs):
        raise FitPartTwistValidationError("Part 旋转来源不能重复")
    projections = []
    used_names: set[str] = set()
    for item in inputs:
        if not item.rotation_plug or not item.rotate_order_plug:
            raise FitPartTwistValidationError("Part 旋转及旋转顺序来源不能为空")
        has_ik = bool(item.ik_rotation_plug or item.ik_rotate_order_plug
                      or item.ik_fk_blend_plug)
        if has_ik and not all((item.ik_rotation_plug,
                               item.ik_rotate_order_plug,
                               item.ik_fk_blend_plug)):
            raise FitPartTwistValidationError("Part IK/FK 投影来源不完整")
        stem = item.start_body.rsplit("|", 1)[-1]
        prefix = f"AdvPy_{stem}_FitPartTwist"
        projection = FitPartTwistProjection(
            item, prefix + "Compose", prefix + "Decompose",
            prefix + "Project",
            prefix + "IkCompose" if has_ik else None,
            prefix + "IkDecompose" if has_ik else None,
            prefix + "IkProject" if has_ik else None,
            prefix + "Blend" if has_ik else None,
        )
        names = (projection.compose_name, projection.decompose_name,
                 projection.project_name)
        names += tuple(name for name in (
            projection.ik_compose_name, projection.ik_decompose_name,
            projection.ik_project_name, projection.blend_name) if name)
        if any(name in used_names for name in names):
            raise FitPartTwistValidationError("Part 投影节点名称重复")
        used_names.update(names)
        projections.append(projection)
    return tuple(projections)


@dataclass(frozen=True, slots=True)
class FitPartTwistStep:
    part_name: str
    start_body: str
    index: int
    count: int
    default_amount: float
    down_twist_plug: str
    up_twist_plug: str | None
    previous_target_plug: str | None
    amount_node: str
    up_amount_node: str | None
    target_node: str
    difference_node: str
    use_offset_parent_matrix: bool = False
    matrix_name: str | None = None

    @property
    def target_plug(self) -> str:
        return self.target_node + ".output1D"

    @property
    def output_plug(self) -> str:
        return self.difference_node + ".output1D"


def plan_fit_part_twist(
    parts: tuple[FitPartJointSpec, ...],
    sources: tuple[FitPartTwistSource, ...],
) -> tuple[FitPartTwistStep, ...]:
    """Plan local Part rotation from cumulative down/up-twist targets.

    For Part i, target(i) = down*amount(i) + up*amount(i) + addition(i).
    Its local X rotation subtracts target(i-1). The first Part optionally
    subtracts the Body's down twist when Body already carries that rotation.
    This describes the non-bendy distribution branch; callers must supply
    the actual rig twist plugs, which are not inferred from joint names.
    """
    by_start: dict[str, list[FitPartJointSpec]] = {}
    for part in parts:
        by_start.setdefault(part.start_body, []).append(part)
    by_source = {source.start_body: source for source in sources}
    if len(by_source) != len(sources) or set(by_source) != set(by_start):
        raise FitPartTwistValidationError(
            "每条 Fit Part 链必须恰有一个扭转来源")
    part_names = {part.name for part in parts}
    for source in sources:
        for plug in (source.down_twist_plug, source.up_twist_plug):
            if plug and plug.split(".", 1)[0].rsplit("|", 1)[-1] in part_names:
                raise FitPartTwistValidationError(
                    "Part 扭转来源不能由同一批 Part 关节输出")
    steps: list[FitPartTwistStep] = []
    used_nodes: set[str] = set()
    for start_body, chain in by_start.items():
        chain.sort(key=lambda part: part.index)
        count = chain[0].count
        if (len(chain) != count or
                [part.index for part in chain] != list(range(1, count + 1)) or
                any(part.count != count for part in chain)):
            raise FitPartTwistValidationError("Part 链编号或数量不连续："
                                              + start_body)
        source = by_source[start_body]
        previous_target = (source.down_twist_plug
                           if source.subtract_body_twist else None)
        for part in chain:
            stem = part.name.rsplit("_", 1)[0]
            side = part.side.value
            prefix = f"AdvPy_{stem}_{side}_FitTwist"
            amount_node = prefix + "Amount"
            up_amount_node = prefix + "UpAmount" if source.up_twist_plug else None
            target_node = prefix + "Target"
            difference_node = prefix + "Local"
            use_opm = not part.segment_scale_compensate
            matrix_name = prefix + "Matrix" if use_opm else None
            names = (amount_node, target_node, difference_node)
            names += (up_amount_node,) if up_amount_node else ()
            names += (matrix_name,) if matrix_name else ()
            if any(name in used_nodes for name in names):
                raise FitPartTwistValidationError("Part 扭转节点名称重复")
            used_nodes.update(names)
            step = FitPartTwistStep(
                part.name, start_body, part.index, count,
                part.index / (count + 1), source.down_twist_plug,
                source.up_twist_plug, previous_target, amount_node,
                up_amount_node, target_node, difference_node,
                use_opm, matrix_name)
            steps.append(step)
            previous_target = step.target_plug
    return tuple(steps)
