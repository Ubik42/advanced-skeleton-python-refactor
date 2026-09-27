"""Spline Inbetween frames derived from the spine's corrected IK outputs."""
from __future__ import annotations

from dataclasses import dataclass

from .fit_part import FitPartJointSpec
from .fit_inbetween_ik_parts import (
    InbetweenIkPartsPlan, plan_inbetween_ik_parts,
)


@dataclass(frozen=True, slots=True)
class InbetweenSplineIkFrame:
    body_part_name: str
    body_part_path: str
    ikx_name: str
    frame_name: str
    blend_name: str
    local_matrix_name: str
    fraction: float
    rotate_order: int


@dataclass(frozen=True, slots=True)
class InbetweenSplineIkPlan:
    root_path: str
    start_output_path: str
    end_output_path: str
    parts: InbetweenIkPartsPlan
    frames: tuple[InbetweenSplineIkFrame, ...]

    @property
    def node_names(self) -> tuple[str, ...]:
        return tuple(name for frame in self.frames for name in (
            frame.ikx_name, frame.frame_name, frame.blend_name,
            frame.local_matrix_name))


def plan_inbetween_spline_ik(
    body_parts: tuple[FitPartJointSpec, ...], *,
    root_path: str, start_output_path: str,
    end_output_path: str,
) -> InbetweenSplineIkPlan:
    """Place IKX frames between adjacent corrected Spline output frames.

    The Spline solver and its rest-pose compensation remain intact. Each
    blended frame is corrected locally by the IKX joint's bind transform,
    so a curved bind spine does not force the Part into the curve's raw frame.
    """
    if (not root_path.startswith("|") or not start_output_path.startswith("|")
            or not end_output_path.startswith("|")
            or len({root_path, start_output_path, end_output_path}) != 3):
        raise ValueError("Spline Inbetween 需要唯一的根和相邻 IK 输出")
    parts = plan_inbetween_ik_parts(
        body_parts, start_ik_driver=start_output_path,
        end_ik_driver=end_output_path)
    ordered = tuple(sorted(body_parts, key=lambda item: item.index))
    frames = tuple(InbetweenSplineIkFrame(
        part.name, part.path, marker.ikx_name,
        "AdvPy_" + part.name + "_SplineIKFrame",
        "AdvPy_" + part.name + "_SplineIKBlend",
        "AdvPy_" + part.name + "_SplineIKLocalMM",
        part.index / (part.count + 1), part.rotation_order,
    ) for part, marker in zip(ordered, parts.parts))
    plan = InbetweenSplineIkPlan(root_path, start_output_path,
                                 end_output_path, parts, frames)
    if len(set(plan.node_names)) != len(plan.node_names):
        raise ValueError("Spline Inbetween IKX 节点名称重复")
    return plan
