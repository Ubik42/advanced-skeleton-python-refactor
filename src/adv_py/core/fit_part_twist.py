"""Host-independent twist distribution for Fit Part chains."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .fit_part import FitPartJointSpec
from .body_limb_controls import BodyLimbFkControlSpec


class FitPartTwistValidationError(ValueError):
    pass


def _plug_reads_body(plug: str | None, body: str) -> bool:
    if not plug:
        return False
    node = plug.split(".", 1)[0]
    return (node == body
            or node.rsplit("|", 1)[-1] == body.rsplit("|", 1)[-1])


@dataclass(frozen=True, slots=True)
class FitPartTwistSource:
    start_body: str
    down_twist_plug: str
    up_twist_plug: str | None = None
    subtract_body_twist: bool = True
    compensate_start_body: bool = False
    body_constraint_name: str | None = None

    def __post_init__(self) -> None:
        if not self.start_body or not self.down_twist_plug:
            raise FitPartTwistValidationError("Part 扭转来源不能为空")
        if (type(self.subtract_body_twist) is not bool
                or type(self.compensate_start_body) is not bool
                or (self.subtract_body_twist
                    and self.compensate_start_body)
                or (self.compensate_start_body
                    and not self.body_constraint_name)):
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
    world_matrix_plug: str | None = None
    distribution_source: bool = True
    fk_world_matrix_plug: str | None = None
    ik_world_matrix_plug: str | None = None
    compensate_start_body: bool = False
    body_constraint_name: str | None = None
    reference_inverse_plug: str | None = None
    static_parent_body: str | None = None
    reference_parent_body: str | None = None


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
    reference_name: str | None = None
    matrix_blend_name: str | None = None
    static_source_name: str | None = None

    @property
    def reference_parent_path(self) -> str | None:
        parent = (self.input.reference_parent_body
                  or self.input.static_parent_body
                  or self.input.start_body.rsplit("|", 1)[0])
        return parent or None

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
            self.input.compensate_start_body,
            self.input.body_constraint_name,
        )


@dataclass(frozen=True, slots=True)
class FitPartTwistControlRewire:
    start_body: str
    static_source_name: str
    compose_name: str
    control_source_path: str

    @property
    def matrix_input(self) -> str:
        return self.compose_name + ".matrixIn[0]"

    @property
    def control_matrix(self) -> str:
        return self.control_source_path + ".worldMatrix[0]"


def plan_generic_fit_part_twist_rewires(
    projections: tuple[FitPartTwistProjection, ...],
    controls: tuple[BodyLimbFkControlSpec, ...],
) -> tuple[FitPartTwistControlRewire, ...]:
    """Replace a temporary static twist source once its FK driver exists."""
    by_body = {control.driven_joint: control for control in controls}
    if len(by_body) != len(controls):
        raise FitPartTwistValidationError(
            "通用 Part Twist 的 FK 驱动关节重复")
    rewires = []
    for projection in projections:
        if projection.static_source_name is None:
            continue
        control = by_body.get(projection.input.start_body)
        if control is None:
            continue
        source = (control.source_override_path
                  or control.sub_control_path or control.control_path)
        if not (source == control.control_path
                or source.startswith(control.control_path + "|")
                or source.startswith(control.offset_path + "|")):
            raise FitPartTwistValidationError(
                "通用 Part Twist 的 FK 来源脱离控制层：" + source)
        rewires.append(FitPartTwistControlRewire(
            projection.input.start_body,
            projection.static_source_name,
            projection.compose_name, source))
    return tuple(rewires)


def plan_standard_fit_part_rotation_inputs(
    parts: tuple[FitPartJointSpec, ...],
    *,
    independent_world_matrices: Mapping[str, str] | None = None,
    independent_body_constraints: Mapping[str, str] | None = None,
    blended_world_matrices: Mapping[
        str, tuple[str, str, str, str]] | None = None,
    reference_inverse_matrices: Mapping[str, str] | None = None,
    semantic_parent_by_body: Mapping[str, str] | None = None,
) -> tuple[FitPartRotationInput, ...]:
    """Resolve independent twist channels for ordinary and Bendy Part chains.

    Standard Arm/Leg chains blend their independent FK/IK driver matrices.
    Other joints use an independent FK source when the rig exposes one.
    Without one, a bind-aligned static source follows the original parent:
    reading the Body world matrix would cycle after Part reparenting.
    A dual-twist child follows the same rule when it has no independent driver.
    """
    starts = {part.start_body: part for part in parts}
    independent_world_matrices = independent_world_matrices or {}
    independent_body_constraints = independent_body_constraints or {}
    blended_world_matrices = blended_world_matrices or {}
    reference_inverse_matrices = reference_inverse_matrices or {}
    semantic_parent_by_body = semantic_parent_by_body or {}
    if set(blended_world_matrices) & set(independent_world_matrices):
        raise FitPartTwistValidationError("Part 独立与混合矩阵来源不能重复")
    for body, blend in blended_world_matrices.items():
        if (not isinstance(blend, tuple) or len(blend) != 4
                or any(not isinstance(plug, str) or not plug
                       for plug in blend)):
            raise FitPartTwistValidationError(
                "Part FK／IK 混合来源不完整：" + body)
    for body, constraint in independent_body_constraints.items():
        matrix = independent_world_matrices.get(body)
        if (not constraint or not matrix
                or matrix == body + ".worldMatrix[0]"):
            raise FitPartTwistValidationError(
                "Body 扭转补偿需要独立的控制矩阵与朝向约束：" + body)
    for body, inverse in reference_inverse_matrices.items():
        if (body not in starts or not isinstance(inverse, str)
                or not inverse.endswith(".worldInverseMatrix[0]")
                or starts[body].start_body_name.rsplit("_", 1)[0]
                in ("Shoulder", "Elbow", "Hip", "Knee")):
            raise FitPartTwistValidationError(
                "Part 参考逆矩阵不属于有效的起点：" + body)
    result = []
    auxiliary = {}
    for start, part in starts.items():
        stem = part.start_body_name.rsplit("_", 1)[0]
        side = part.side.value
        up = None
        if part.dual_twist_child:
            child = part.end_body
            child_name = child.rsplit("|", 1)[-1]
            child_matrix = independent_world_matrices.get(child)
            child_blend = blended_world_matrices.get(child)
            up = (f"AdvPy_{child_name}_FitPartTwistProject"
                  ".outputRotateX")
            auxiliary[child] = FitPartRotationInput(
                child, "", child + ".rotateOrder",
                world_matrix_plug=child_matrix,
                distribution_source=False,
                fk_world_matrix_plug=(child_blend[0]
                                      if child_blend else None),
                ik_world_matrix_plug=(child_blend[1]
                                      if child_blend else None),
                ik_fk_blend_plug=(child_blend[2]
                                  if child_blend else None),
                static_parent_body=(start if not (child_matrix or child_blend)
                                    else None),
                reference_parent_body=semantic_parent_by_body.get(child))
        if (stem in ("Shoulder", "Elbow", "Hip", "Knee")
                and start not in independent_world_matrices):
            limb = "Arm" if stem in ("Shoulder", "Elbow") else "Leg"
            blend = blended_world_matrices.get(start)
            result.append(FitPartRotationInput(
                start, "", start + ".rotateOrder", up,
                ik_fk_blend_plug=(blend[2] if blend else
                    f"AdvPy_{limb}Settings.{limb.lower()}IkFk_{side}"),
                fk_world_matrix_plug=(blend[0] if blend else
                    f"AdvPy_{stem}FKDriver_{side}.worldMatrix[0]"),
                ik_world_matrix_plug=(blend[1] if blend else
                    f"AdvPy_{stem}IKDriver_{side}.worldMatrix[0]"),
                subtract_body_twist=False,
                compensate_start_body=True,
                body_constraint_name=(blend[3] if blend else
                    f"AdvPy_{stem}IKFKBlend_{side}"),
                reference_parent_body=semantic_parent_by_body.get(start)))
        else:
            blend = blended_world_matrices.get(start)
            independent = independent_world_matrices.get(start)
            constraint = (blend[3] if blend else
                          independent_body_constraints.get(start))
            result.append(FitPartRotationInput(
                start, "", start + ".rotateOrder",
                up_twist_plug=up,
                world_matrix_plug=None if blend else independent,
                fk_world_matrix_plug=blend[0] if blend else None,
                ik_world_matrix_plug=blend[1] if blend else None,
                ik_fk_blend_plug=blend[2] if blend else None,
                subtract_body_twist=not bool(constraint),
                compensate_start_body=bool(constraint),
                body_constraint_name=constraint,
                reference_inverse_plug=reference_inverse_matrices.get(start),
                static_parent_body=(semantic_parent_by_body.get(
                    start, start.rsplit("|", 1)[0])
                                    if not (blend or independent) else None),
                reference_parent_body=semantic_parent_by_body.get(start)))
    # An up-twist child may itself start a Part chain. Its primary projection
    # already supplies the child channel; a second auxiliary projection would
    # duplicate both the start key and the Maya node names.
    return tuple(result) + tuple(
        input for child, input in auxiliary.items() if child not in starts)


def plan_fit_part_twist_projections(
    inputs: tuple[FitPartRotationInput, ...],
) -> tuple[FitPartTwistProjection, ...]:
    if len({item.start_body for item in inputs}) != len(inputs):
        raise FitPartTwistValidationError("Part 旋转来源不能重复")
    projections = []
    used_names: set[str] = set()
    for item in inputs:
        blended_matrix = bool(item.fk_world_matrix_plug
                              or item.ik_world_matrix_plug)
        if (not item.rotate_order_plug
                or sum(bool(mode) for mode in (
                    item.rotation_plug, item.world_matrix_plug,
                    blended_matrix, item.static_parent_body)) != 1):
            raise FitPartTwistValidationError("Part 旋转及旋转顺序来源不能为空")
        if _plug_reads_body(item.world_matrix_plug, item.start_body):
            raise FitPartTwistValidationError(
                "Part 改挂后不能从起点 Body 世界矩阵读取扭转："
                + item.start_body)
        if (item.reference_parent_body
                and not item.start_body.startswith(
                    item.reference_parent_body + "|")):
            raise FitPartTwistValidationError(
                "Part 矩阵参照必须位于起点 Body 的原父链")
        if type(item.distribution_source) is not bool:
            raise FitPartTwistValidationError("Part 扭转投影用途无效")
        if item.static_parent_body and (
                not item.start_body.startswith(
                    item.static_parent_body + "|")
                or item.reference_inverse_plug is not None):
            raise FitPartTwistValidationError(
                "静态 Twist 来源必须使用原 Body 父级的绑定参考")
        if (type(item.compensate_start_body) is not bool
                or (item.compensate_start_body
                    and (item.subtract_body_twist
                         or not item.body_constraint_name))):
            raise FitPartTwistValidationError("Body 扭转补偿配置冲突")
        if blended_matrix and not all((item.fk_world_matrix_plug,
                                       item.ik_world_matrix_plug,
                                       item.ik_fk_blend_plug)):
            raise FitPartTwistValidationError("Part FK／IK 矩阵来源不完整")
        if (item.world_matrix_plug or blended_matrix
                or item.static_parent_body) and any((
                item.ik_rotation_plug, item.ik_rotate_order_plug)):
            raise FitPartTwistValidationError(
                "矩阵参照投影不能同时指定 IK/FK 旋转混合")
        if item.world_matrix_plug and item.ik_fk_blend_plug:
            raise FitPartTwistValidationError("单一矩阵来源不能指定 IK/FK 权重")
        if item.reference_inverse_plug is not None and (
                not isinstance(item.reference_inverse_plug, str)
                or not item.reference_inverse_plug.endswith(
                    ".worldInverseMatrix[0]")
                or not (item.world_matrix_plug or blended_matrix
                        or item.static_parent_body)):
            raise FitPartTwistValidationError(
                "参考逆矩阵要求世界矩阵扭转来源")
        has_ik = bool(item.rotation_plug and (
            item.ik_rotation_plug or item.ik_rotate_order_plug
            or item.ik_fk_blend_plug))
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
            prefix + "Reference" if ((item.world_matrix_plug
                                      or blended_matrix or item.static_parent_body)
                                     and item.reference_inverse_plug is None)
            else None,
            prefix + "WorldBlend" if blended_matrix else None,
            prefix + "StaticSource" if item.static_parent_body else None,
        )
        names = (projection.compose_name, projection.decompose_name,
                 projection.project_name)
        names += tuple(name for name in (
            projection.ik_compose_name, projection.ik_decompose_name,
                 projection.ik_project_name, projection.blend_name,
                 projection.reference_name,
                 projection.matrix_blend_name,
                 projection.static_source_name) if name)
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
    compensate_start_body: bool = False
    body_constraint_name: str | None = None

    @property
    def body_compensation_nodes(self) -> tuple[str, ...]:
        if not self.compensate_start_body:
            return ()
        stem = self.start_body.rsplit("|", 1)[-1]
        prefix = f"AdvPy_{stem}_FitTwistBody"
        return (prefix + "Weight", prefix + "Amount",
                prefix + "Offset")

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
            if _plug_reads_body(plug, source.start_body):
                raise FitPartTwistValidationError(
                    "Part 扭转来源不能读取改挂后的起点 Body："
                    + source.start_body)
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
        if any(_plug_reads_body(plug, chain[0].end_body)
               for plug in (source.down_twist_plug, source.up_twist_plug)):
            raise FitPartTwistValidationError(
                "Part 扭转来源不能读取改挂后的下游 Body："
                + chain[0].end_body)
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
            step = FitPartTwistStep(
                part.name, start_body, part.index, count,
                part.index / (count + 1), source.down_twist_plug,
                source.up_twist_plug, previous_target, amount_node,
                up_amount_node, target_node, difference_node,
                use_opm, matrix_name,
                part.index == 1 and source.compensate_start_body,
                source.body_constraint_name if part.index == 1 else None)
            names = (amount_node, target_node, difference_node)
            names += (up_amount_node,) if up_amount_node else ()
            names += (matrix_name,) if matrix_name else ()
            names += step.body_compensation_nodes
            if any(name in used_nodes for name in names):
                raise FitPartTwistValidationError("Part 扭转节点名称重复")
            used_nodes.update(names)
            steps.append(step)
            previous_target = step.target_plug
    return tuple(steps)
