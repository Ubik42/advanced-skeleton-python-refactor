"""Translate temporary Fit Inbetween guides into final Body Part joints."""
from __future__ import annotations

from dataclasses import dataclass

from .body_skeleton import BodyJointSpec
from .fit_inbetween import FitInbetweenPlan
from .fit_part import FitPartJointSpec
from .fit_symmetry import FitSymmetryInstance


@dataclass(frozen=True, slots=True)
class FitInbetweenBodyPlan:
    parts: tuple[FitPartJointSpec, ...]


def plan_fit_inbetween_body(
    guides: FitInbetweenPlan,
    instances: tuple[FitSymmetryInstance, ...],
    body_specs: tuple[BodyJointSpec, ...],
) -> FitInbetweenBodyPlan:
    """Insert Inbetween influences after the standard Body rig is planned.

    The temporary Fit guides supply original interpolation values. The
    generated Body Parts use the same final names and hierarchy as the MEL
    build, while the standard rig can still be planned from direct Body links.
    """
    by_source_side = {(item.source_joint, item.side): item
                      for item in instances}
    by_body_path = {item.path: item for item in body_specs}
    if (len(by_source_side) != len(instances)
            or len(by_body_path) != len(body_specs)):
        raise ValueError("Inbetween Body 需要唯一的对称展开关节")
    parts = []
    used_names = {item.name for item in body_specs}
    for guide in guides.guides:
        starts = [item for item in instances
                  if item.source_joint == guide.start_joint]
        if not starts:
            raise ValueError("Inbetween 起点没有 Body 对称实例："
                             + guide.start_joint)
        for start in starts:
            end = by_source_side.get((guide.end_joint, start.side))
            if end is None or end.parent_output_path != start.output_path:
                raise ValueError("Inbetween 终点与起点 Body 侧别或父级不一致："
                                 + guide.end_joint)
            start_spec = by_body_path[start.output_path]
            name = guide.name + "_" + start.side.value
            if name in used_names:
                raise ValueError("Inbetween Body Part 名称重复：" + name)
            used_names.add(name)
            parent_name = (start.output_name if guide.index == 1 else
                           guide.name.rsplit("Part", 1)[0]
                           + "Part" + str(guide.index - 1)
                           + "_" + start.side.value)
            parent_path = (start.output_path if guide.index == 1 else
                           next(item.path for item in parts
                                if item.name == parent_name))
            position = guide.world_position
            if start.mirrored:
                position = (-position[0], position[1], position[2])
            parts.append(FitPartJointSpec(
                guide.start_joint, start.output_path, end.output_path,
                start.side, guide.index, guide.count,
                parent_path + "|" + name, name, parent_path,
                position, guide.deform_profile,
                start_spec.skin_enabled, guide.rotation_order,
                False, "inbetween",
            ))
    return FitInbetweenBodyPlan(tuple(parts))
