"""Insert Inbetween and Twist Part chains into one final Body hierarchy."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.fit_inbetween import FitInbetweenPlan
from adv_py.core.fit_inbetween_body import plan_fit_inbetween_body
from adv_py.core.fit_part import plan_fit_part_reparents

from .body_skeleton import BodySkeletonBuildPlan
from .fit_part import BuildFitPartHierarchy, FitPartHierarchyHost


def plan_combined_part_hierarchy(
    body: BodySkeletonBuildPlan,
    inbetween: FitInbetweenPlan,
) -> BodySkeletonBuildPlan:
    if not body.ready:
        raise ValueError("Inbetween Body 需要完整的标准骨架计划")
    addition = plan_fit_inbetween_body(
        inbetween, body.symmetry.instances, body.specs)
    parts = body.fit_parts + addition.parts
    names = [part.name for part in parts]
    if len(set(names)) != len(names):
        raise ValueError("Twist 与 Inbetween Part 名称冲突")
    reparents = plan_fit_part_reparents(
        body.symmetry.instances, body.symmetry.source.metadata, parts)
    return replace(body, fit_parts=parts,
                   fit_part_reparents=reparents)


class BuildCombinedFitPartHierarchy:
    def __init__(self, host: FitPartHierarchyHost) -> None:
        self._host = host

    def apply(
        self, body: BodySkeletonBuildPlan,
        inbetween: FitInbetweenPlan,
    ):
        combined = plan_combined_part_hierarchy(body, inbetween)
        return BuildFitPartHierarchy(self._host).apply(combined)
