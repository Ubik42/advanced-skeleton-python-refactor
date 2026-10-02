"""Spline Inbetween frames derived from the spine's corrected IK outputs."""
from __future__ import annotations

from dataclasses import dataclass,replace

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
    native_output_path: str | None = None


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
            frame.ikx_name, frame.frame_name,
            *((frame.blend_name,frame.local_matrix_name) if frame.native_output_path is None else ())))


def plan_inbetween_spline_ik(
    body_parts: tuple[FitPartJointSpec, ...], *,
    root_path: str, start_output_path: str,
    end_output_path: str, native_outputs: tuple[str,...]=(),
) -> InbetweenSplineIkPlan:
    """Use each expanded native output for source Fits.

    The optional interpolation layout remains only for the older generic
    character builder, which does not yet author a full Fit-derived chain.
    """
    if (not root_path.startswith("|") or not start_output_path.startswith("|")
            or not end_output_path.startswith("|")
            or len({root_path, start_output_path, end_output_path}) != 3
            or not start_output_path.startswith(root_path + "|")
            or not end_output_path.startswith(root_path + "|")):
        raise ValueError("Spline Inbetween 需要唯一的根和相邻 IK 输出")
    parts = plan_inbetween_ik_parts(
        body_parts, start_ik_driver=start_output_path,
        end_ik_driver=end_output_path)
    ordered = tuple(sorted(body_parts, key=lambda item: item.index))
    if native_outputs and (len(native_outputs)!=len(ordered)
            or len(set(native_outputs))!=len(native_outputs)
            or any(not output.startswith(root_path+'|') for output in native_outputs)):
        raise ValueError('Spline Part 原生输出与 Part 链不一致')
    frames = tuple(InbetweenSplineIkFrame(
        part.name, part.path, marker.ikx_name,
        "AdvPy_" + part.name + "_SplineIKFrame",
        "AdvPy_" + part.name + "_SplineIKBlend",
        "AdvPy_" + part.name + "_SplineIKLocalMM",
        part.index / (part.count + 1), part.rotation_order,
    ) for part, marker in zip(ordered, parts.parts))
    if native_outputs:
        frames=tuple(replace(frame,native_output_path=output) for frame,output in zip(frames,native_outputs))
        parts=replace(parts,parts=tuple(replace(part,parent_ikx_name=output+'|'+frame.frame_name)
             for part,frame,output in zip(parts.parts,frames,native_outputs)))
    plan = InbetweenSplineIkPlan(root_path, start_output_path,
                                 end_output_path, parts, frames)
    if len(set(plan.node_names)) != len(plan.node_names):
        raise ValueError("Spline Inbetween IKX 节点名称重复")
    return plan
