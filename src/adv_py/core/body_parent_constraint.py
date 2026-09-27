"""Source-shaped plan for ADV 6.925 ``asParentConstraint``.

The command has two branches: Maya parent/scale constraints, or a multMatrix
graph feeding offsetParentMatrix (optionally via pickMatrix/decomposeMatrix).
The caller supplies the maintain-offset matrix captured from the scene.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


Matrix16 = tuple[float, ...]
PARENT_CONSTRAINT_FLAGS = frozenset((
    "-mo", "-skipScale", "-includePickMatrix", "-UDM", "-FMM"))


def parse_body_parent_constraint_flags(
    flags: tuple[str, ...],
) -> tuple[bool, bool, bool, bool, bool]:
    if (not isinstance(flags, tuple)
            or any(not isinstance(flag, str) for flag in flags)
            or len(flags) != len(set(flags))
            or not set(flags) <= PARENT_CONSTRAINT_FLAGS):
        raise ValueError("Body Parent Constraint 选项无效")
    return tuple(flag in flags for flag in (
        "-mo", "-skipScale", "-includePickMatrix", "-UDM", "-FMM"))


@dataclass(frozen=True, slots=True)
class BodyParentConstraintInput:
    driver: str
    driven: str
    driven_parent: str | None
    driven_is_joint: bool
    rotate_order: int
    use_offset_parent_matrix: bool
    maintain_offset: bool = False
    skip_scale: bool = False
    include_pick_matrix: bool = False
    use_decompose_matrix: bool = False
    force_mult_matrix: bool = False
    offset_matrix: Matrix16 | None = None
    existing_mult_matrix: bool = False
    existing_pick_matrix: bool = False


@dataclass(frozen=True, slots=True)
class BodyParentConstraintPlan:
    input: BodyParentConstraintInput
    mode: str
    mult_matrix: str | None
    pick_matrix: str | None
    decompose_matrix: str | None
    matrix_inputs: tuple[tuple[int, str | Matrix16], ...]
    output_connections: tuple[tuple[str, str], ...]
    create_nodes: tuple[tuple[str, str], ...]
    reset_local_transform: bool
    reset_joint_orient: bool


@dataclass(frozen=True, slots=True)
class BodyParentConstraintState:
    node_types: tuple[tuple[str, str], ...]
    matrix_inputs: tuple[tuple[int, str | Matrix16], ...]
    output_connections: tuple[tuple[str, str], ...]
    local_translate: tuple[float, float, float]
    local_rotate: tuple[float, float, float]
    local_scale: tuple[float, float, float]
    joint_orient: tuple[float, float, float] | None
    pick_use_scale: bool | None
    decompose_rotate_order: int | None


def _node_stem(driven: str) -> tuple[str, str]:
    leaf = driven.rsplit("|", 1)[-1]
    if not leaf:
        raise ValueError("约束目标名称无效")
    stem, separator, side = leaf.rpartition("_")
    if not separator or not stem or not side:
        raise ValueError("约束目标缺少名称与侧别后缀")
    return stem, "_" + side


def plan_body_parent_constraint(
    source: BodyParentConstraintInput,
) -> BodyParentConstraintPlan:
    if not isinstance(source, BodyParentConstraintInput):
        raise ValueError("Body Parent Constraint 输入类型无效")
    for path in (source.driver, source.driven):
        if not isinstance(path, str) or not path:
            raise ValueError("Body Parent Constraint 节点名称不能为空")
    if (source.driven_parent is not None
            and (not isinstance(source.driven_parent, str)
                 or not source.driven_parent)):
        raise ValueError("约束目标父级无效")
    if (type(source.driven_is_joint) is not bool
            or type(source.use_offset_parent_matrix) is not bool
            or type(source.rotate_order) is not int
            or not 0 <= source.rotate_order <= 5
            or any(type(value) is not bool for value in (
                source.maintain_offset, source.skip_scale,
                source.include_pick_matrix, source.use_decompose_matrix,
                source.force_mult_matrix, source.existing_mult_matrix,
                source.existing_pick_matrix))):
        raise ValueError("Body Parent Constraint 开关或旋转顺序无效")
    if source.maintain_offset:
        if (source.offset_matrix is None
                or len(source.offset_matrix) != 16
                or any(type(value) not in (int, float) or not isfinite(value)
                       for value in source.offset_matrix)):
            raise ValueError("保持偏移需要 4×4 矩阵")
    elif source.offset_matrix is not None:
        raise ValueError("未启用保持偏移却传入偏移矩阵")

    if not (source.use_offset_parent_matrix or source.force_mult_matrix):
        outputs = [(source.driver, source.driven + ".parentConstraint")]
        if not source.skip_scale:
            outputs.append((source.driver, source.driven + ".scaleConstraint"))
        return BodyParentConstraintPlan(
            source, "constraint", None, None, None, (),
            tuple(outputs), (), False, False)

    name, side = _node_stem(source.driven)
    mm = name + "MM" + side
    pm = name + "PM" + side
    dm = name + "DM" + side
    matrix_inputs: list[tuple[int, str | Matrix16]] = []
    index = 0
    if source.maintain_offset:
        matrix_inputs.append((index, source.offset_matrix))
        index += 1
    matrix_inputs.append((index, source.driver + ".worldMatrix[0]"))
    index += 1
    if source.driven_parent is not None:
        matrix_inputs.append((index, source.driven_parent
                              + ".worldInverseMatrix[0]"))

    pick = source.include_pick_matrix or source.skip_scale
    decompose = (not source.use_offset_parent_matrix
                 or (source.use_decompose_matrix and not pick))
    outputs: list[tuple[str, str]] = []
    nodes = [] if source.existing_mult_matrix else [(mm, "multMatrix")]
    if pick:
        nodes.append((pm, "pickMatrix"))
        outputs.append((mm + ".matrixSum", pm + ".inputMatrix"))
    if decompose:
        nodes.append((dm, "decomposeMatrix"))
        upstream = (pm + ".outputMatrix" if pick or (
            source.use_decompose_matrix and source.existing_pick_matrix)
                    else mm + ".matrixSum")
        outputs.append((upstream, dm + ".inputMatrix"))
        if not pick and source.use_decompose_matrix:
            outputs.extend((dm + ".output" + output,
                            source.driven + "." + target)
                           for output, target in (("Translate", "t"),
                                                  ("Rotate", "r"),
                                                  ("Scale", "s"),
                                                  ("Shear", "sh")))
        else:
            for upper, lower, shear in zip("XYZ", "xyz", ("xy", "xz", "yz")):
                outputs.extend((
                    (dm + ".outputTranslate" + upper,
                     source.driven + ".t" + lower),
                    (dm + ".outputRotate" + upper,
                     source.driven + ".r" + lower),
                    (dm + ".outputScale" + upper,
                     source.driven + ".s" + lower),
                    (dm + ".outputShear" + upper,
                     source.driven + ".sh" + shear),
                ))
        mode = "pick_decompose" if pick else "decompose_matrix"
    else:
        outputs.append(((pm + ".outputMatrix" if pick else mm + ".matrixSum"),
                        source.driven + ".offsetParentMatrix"))
        mode = "pick_matrix" if pick else "mult_matrix"
    return BodyParentConstraintPlan(
        source, mode, mm, pm if pick or source.existing_pick_matrix else None,
        dm if decompose else None,
        tuple(matrix_inputs), tuple(outputs), tuple(nodes), True,
        source.driven_is_joint)


def audit_body_parent_constraint(
    plan: BodyParentConstraintPlan,
    state: BodyParentConstraintState,
) -> tuple[str, ...]:
    issues = []
    nodes = dict(state.node_types)
    for name, kind in plan.create_nodes:
        if nodes.get(name) != kind:
            issues.append(name + " 节点类型不符")
    if plan.mult_matrix is not None and nodes.get(plan.mult_matrix) != "multMatrix":
        issues.append("缺少 multMatrix")
    if plan.pick_matrix is not None and nodes.get(plan.pick_matrix) != "pickMatrix":
        issues.append("缺少 pickMatrix")
    if plan.decompose_matrix is not None and nodes.get(
            plan.decompose_matrix) != "decomposeMatrix":
        issues.append("缺少 decomposeMatrix")
    if (plan.matrix_inputs != state.matrix_inputs
            or plan.output_connections != state.output_connections):
        issues.append("约束驱动连接不符")
    if plan.reset_local_transform and (
            state.local_translate != (0.0, 0.0, 0.0)
            or state.local_rotate != (0.0, 0.0, 0.0)
            or state.local_scale != (1.0, 1.0, 1.0)):
        issues.append("目标本地 TRS 未归零")
    if plan.reset_joint_orient and state.joint_orient != (0.0, 0.0, 0.0):
        issues.append("目标 jointOrient 未归零")
    if plan.mode in ("pick_matrix", "pick_decompose") and state.pick_use_scale != (
            not plan.input.skip_scale):
        issues.append("PickMatrix 缩放开关不符")
    if plan.decompose_matrix is not None and state.decompose_rotate_order != (
            plan.input.rotate_order):
        issues.append("decomposeMatrix 旋转顺序不符")
    return tuple(issues)
