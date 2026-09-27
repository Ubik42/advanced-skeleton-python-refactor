"""Build one Inbetween FK source graph within a single host transaction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adv_py.core.fit_inbetween_bias import (
    InbetweenBiasPlan, plan_inbetween_bias,
)
from adv_py.core.fit_inbetween_fk_anchor import (
    InbetweenFkAnchorPlan, plan_inbetween_fk_anchor,
)
from adv_py.core.fit_inbetween_fk_parts import (
    InbetweenFkPartsPlan, plan_inbetween_fk_parts,
)
from adv_py.core.fit_part import FitPartJointSpec
from adv_py.core.fit_inbetween_matrix import (
    InbetweenMatrixDestination, InbetweenMatrixPlan,
    plan_inbetween_matrices, plan_inbetween_matrix_destinations,
)

from .fit_inbetween_bias import InbetweenBiasHost
from .fit_inbetween_fk_anchor import InbetweenFkAnchorHost
from .fit_inbetween_fk_parts import InbetweenFkPartsHost
from .fit_inbetween_matrix import InbetweenMatrixHost


class InbetweenFkGraphHost(
    InbetweenFkAnchorHost, InbetweenFkPartsHost,
    InbetweenBiasHost, InbetweenMatrixHost,
    Protocol,
):
    pass


@dataclass(frozen=True, slots=True)
class InbetweenFkGraphResult:
    anchor: InbetweenFkAnchorPlan
    bias: InbetweenBiasPlan
    matrices: InbetweenMatrixPlan
    destinations: tuple[InbetweenMatrixDestination, ...]
    parts: InbetweenFkPartsPlan | None = None


class BuildInbetweenFkGraph:
    """Build FK sources/receivers; no Body joint is driven implicitly."""

    def __init__(self, host: InbetweenFkGraphHost) -> None:
        self._host = host

    def apply(
        self, start_body_name: str,
        part_names: tuple[str, ...], *,
        fk_offset_path: str,
        fk_control_path: str,
        rotate_order: int,
        part_fk_matrix_plugs: tuple[str, ...],
    ) -> InbetweenFkGraphResult:
        anchor = plan_inbetween_fk_anchor(
            start_body_name, fk_offset_path=fk_offset_path,
            fk_control_path=fk_control_path, rotate_order=rotate_order)
        bias = plan_inbetween_bias(
            start_body_name, part_names, fk_control_path + ".bias")
        matrices = plan_inbetween_matrices(
            bias, base_world_plug=anchor.base_world_plug,
            target_world_plug=anchor.target_world_plug,
            parent_inverse_plug=anchor.parent_inverse_plug)
        destinations = plan_inbetween_matrix_destinations(
            matrices, start_fkx_opm_plug=anchor.start_fkx_opm_plug,
            part_fk_matrix_plugs=part_fk_matrix_plugs)
        return self._build(anchor, bias, matrices, destinations, None)

    def apply_with_parts(
        self, start_body_name: str,
        body_parts: tuple[FitPartJointSpec, ...], *,
        fk_offset_path: str,
        fk_control_path: str,
        fk_system_path: str,
        rotate_order: int,
        part_control_radius: float,
    ) -> InbetweenFkGraphResult:
        """Create every Part receiver and connect the FK graph atomically."""
        anchor = plan_inbetween_fk_anchor(
            start_body_name, fk_offset_path=fk_offset_path,
            fk_control_path=fk_control_path, rotate_order=rotate_order)
        parts = plan_inbetween_fk_parts(
            anchor, body_parts, fk_system_path=fk_system_path,
            radius=part_control_radius)
        bias = plan_inbetween_bias(
            start_body_name, tuple(part.part_name for part in parts.parts),
            fk_control_path + ".bias")
        matrices = plan_inbetween_matrices(
            bias, base_world_plug=anchor.base_world_plug,
            target_world_plug=anchor.target_world_plug,
            parent_inverse_plug=anchor.parent_inverse_plug)
        destinations = plan_inbetween_matrix_destinations(
            matrices, start_fkx_opm_plug=anchor.start_fkx_opm_plug,
            part_fk_matrix_plugs=parts.receiver_plugs)
        return self._build(anchor, bias, matrices, destinations, parts)

    def _build(
        self,
        anchor: InbetweenFkAnchorPlan,
        bias: InbetweenBiasPlan,
        matrices: InbetweenMatrixPlan,
        destinations: tuple[InbetweenMatrixDestination, ...],
        parts: InbetweenFkPartsPlan | None,
    ) -> InbetweenFkGraphResult:
        self._host.preflight_inbetween_fk_anchor(anchor)
        self._host.preflight_inbetween_bias(bias)
        with self._host.transaction("构建 Inbetween FK 图"):
            self._host.create_inbetween_fk_anchor(anchor)
            if self._host.capture_inbetween_fk_anchor(anchor) != (
                    anchor.base_world_plug, anchor.target_world_plug,
                    anchor.parent_inverse_plug, anchor.start_fkx_opm_plug):
                raise RuntimeError("Inbetween FK 起点层不完整："
                                   + anchor.start_body_name)
            if parts is not None:
                self._host.preflight_inbetween_fk_parts(parts)
                for part in parts.parts:
                    self._host.create_inbetween_fk_part(parts, part)
                for part in parts.parts:
                    if (self._host.capture_inbetween_fk_part_receiver(
                            parts, part) != part.receiver_plug):
                        raise RuntimeError("Inbetween Part FK 接收端不完整："
                                           + part.part_name)
                self._host.connect_inbetween_fk_visibility(parts)
                if not self._host.capture_inbetween_fk_visibility(parts):
                    raise RuntimeError("Inbetween Part FK 显示通道不完整")
            self._host.create_inbetween_bias(bias)
            if self._host.capture_inbetween_bias_outputs(bias) != (
                    bias.start_curve.name + ".outValue",
                    bias.mid_curve.name + ".outValue",
                    bias.end_curve.name + ".outValue"):
                raise RuntimeError("Inbetween FK Bias 输出不完整："
                                   + anchor.start_body_name)
            self._host.preflight_inbetween_matrices(matrices)
            for step in matrices.steps:
                self._host.create_inbetween_matrix_step(matrices, step)
            if any(self._host.capture_inbetween_matrix_output(step)
                   != step.output_plug for step in matrices.steps):
                raise RuntimeError("Inbetween FK 矩阵来源不完整："
                                   + anchor.start_body_name)
            self._host.preflight_inbetween_matrix_destinations(destinations)
            for destination in destinations:
                self._host.connect_inbetween_matrix_destination(destination)
            if any(self._host.capture_inbetween_matrix_destination(item)
                   != item.source_plug for item in destinations):
                raise RuntimeError("Inbetween FK 矩阵接收端不完整："
                                   + anchor.start_body_name)
        return InbetweenFkGraphResult(
            anchor, bias, matrices, destinations, parts)
