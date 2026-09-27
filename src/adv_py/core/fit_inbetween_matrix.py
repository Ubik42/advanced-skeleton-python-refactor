"""Plan the 6.925 Inbetween base/target matrix blend for each segment."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_inbetween_bias import InbetweenBiasPlan


@dataclass(frozen=True, slots=True)
class InbetweenMatrixStep:
    joint_name: str
    index: int
    blend_name: str
    local_matrix_name: str
    weight_plug: str
    rotation_only: bool
    legacy_blend_decompose_name: str | None = None
    legacy_target_decompose_name: str | None = None
    legacy_compose_name: str | None = None

    @property
    def output_plug(self) -> str:
        return self.local_matrix_name + ".matrixSum"


@dataclass(frozen=True, slots=True)
class InbetweenMatrixPlan:
    bias: InbetweenBiasPlan
    base_world_plug: str
    target_world_plug: str
    parent_inverse_plug: str
    steps: tuple[InbetweenMatrixStep, ...]


@dataclass(frozen=True, slots=True)
class InbetweenMatrixDestination:
    joint_name: str
    source_plug: str
    target_plug: str


def plan_inbetween_matrix_destinations(
    plan: InbetweenMatrixPlan, *,
    start_fkx_opm_plug: str,
    part_fk_matrix_plugs: tuple[str, ...],
) -> tuple[InbetweenMatrixDestination, ...]:
    """Name the FKX/Part FKMM receivers used by the original OPM path.

    Receivers are supplied explicitly: the current Body control hierarchy
    cannot infer the original FKX and FKMM nodes from a Body joint name.
    """
    plugs = (start_fkx_opm_plug,) + part_fk_matrix_plugs
    if (len(plugs) != len(plan.steps) or not all(plugs)
            or len(set(plugs)) != len(plugs)
            or not start_fkx_opm_plug.endswith(".offsetParentMatrix")
            or any(not plug.endswith(".matrixIn[0]")
                   for plug in part_fk_matrix_plugs)):
        raise ValueError("Inbetween FK 矩阵接收端数量或名称无效")
    return tuple(InbetweenMatrixDestination(
        step.joint_name, step.output_plug, target)
        for step, target in zip(plan.steps, plugs))


def plan_inbetween_matrices(
    bias: InbetweenBiasPlan,
    *,
    base_world_plug: str,
    target_world_plug: str,
    parent_inverse_plug: str,
) -> InbetweenMatrixPlan:
    """Describe original blendMatrix -> multMatrix sources for Body/FK.

    The first step is the start joint; following steps are ordered Part1…N.
    A caller supplies the actual FK base, FK target and parent-inverse plugs,
    because their scene paths depend on the constructed control hierarchy.
    """
    if not all((base_world_plug, target_world_plug,
                parent_inverse_plug)):
        raise ValueError("Inbetween 矩阵来源不能为空")
    names = (bias.start_body_name,) + bias.part_names
    if len(set(names)) != len(names):
        raise ValueError("Inbetween 矩阵目标关节名称重复")
    steps = []
    for index, joint in enumerate(names):
        prefix = "AdvPy_" + joint + "_Inbetween"
        steps.append(InbetweenMatrixStep(
            joint, index, prefix + "Blend", prefix + "LocalMatrix",
            bias.curve_for_index(index).name + ".outValue",
            index > 0,
            prefix + "LegacyBlendDecompose" if index == 0 else None,
            prefix + "LegacyTargetDecompose" if index == 0 else None,
            prefix + "LegacyCompose" if index == 0 else None,
        ))
    return InbetweenMatrixPlan(
        bias, base_world_plug, target_world_plug,
        parent_inverse_plug, tuple(steps))
