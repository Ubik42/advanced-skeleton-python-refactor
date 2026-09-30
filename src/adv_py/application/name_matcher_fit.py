"""Place the standard ADV Fit from editable NameMatcher rows."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.body_hand_fit import synthetic_body_with_hand_source_fit_template
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.name_matcher_fit import (
    NameMatcherFitPlan, NameMatcherRow, NameMatcherRules,
    plan_name_matcher_fit)

from .body_hand_fit import (BuildSyntheticBodyWithHandSourceFit,
                            body_with_hand_orientation_request)
from .fit_container import CreateFitSkeleton
from .fit_orientation_auto import OrientFitJoints
from .registered_body_build import _JoinedTransactionHost


@dataclass(frozen=True, slots=True)
class NameMatcherFitResult:
    placed: int
    missing: tuple[str, ...]
    scale: float
    source_root: str


class BuildNameMatchedFit:
    def __init__(self, host):
        self._host = host

    def plan(self, source_root: str, rows: tuple[NameMatcherRow, ...],
             rules: NameMatcherRules) -> NameMatcherFitPlan:
        host = self._host
        source = host.capture_source_skeleton(source_root)
        axis = host.scene_up_axis().value
        template = synthetic_body_with_hand_source_fit_template(
            host.scene_up_axis())
        return plan_name_matcher_fit(template, tuple(
            (joint.path, joint.name, joint.world_position)
            for joint in source), rows, rules, up_axis=axis)

    def apply(self, source_root: str, rows: tuple[NameMatcherRow, ...],
              rules: NameMatcherRules,
              container: str = 'FitSkeleton') -> NameMatcherFitResult:
        host = self._host
        if host.find_name_collisions(container):
            raise FitSkeletonValidationError(
                'NameMatcher 目标 FitSkeleton 已存在，请先明确处理旧 Fit')
        before = host.capture_source_skeleton(source_root)
        skin_boundary = host.capture_name_matcher_skin_boundary(source_root)
        plan = self.plan(source_root, rows, rules)
        template = synthetic_body_with_hand_source_fit_template(
            host.scene_up_axis(), scale=plan.scale)
        collisions = tuple(joint.name for joint in template.joints
            if host.find_name_collisions(joint.name))
        with host.transaction('NameMatcher 创建并放置 FitSkeleton'):
            if host.capture_source_skeleton(source_root) != before:
                raise FitSkeletonValidationError(
                    'NameMatcher 来源骨架在执行前发生变化')
            current_root = source_root
            if collisions:
                current_root = host.namespace_name_matcher_source(source_root)
            current_source = host.capture_source_skeleton(current_root)
            if tuple((joint.name.rsplit(':', 1)[-1],
                      joint.world_position) for joint in current_source) != tuple(
                      (joint.name.rsplit(':', 1)[-1],
                       joint.world_position) for joint in before):
                raise RuntimeError('NameMatcher 来源改名改变了骨架位置')
            if (host.capture_name_matcher_skin_boundary(current_root)
                    != skin_boundary):
                raise RuntimeError('NameMatcher 来源改名改变了 Skin 连接')
            joined = _JoinedTransactionHost(host)
            CreateFitSkeleton(joined).apply(container)
            built = BuildSyntheticBodyWithHandSourceFit(joined).apply(
                container, scale=plan.scale)
            paths = dict(zip((joint.name for joint in
                built.plan.template_plan.template.joints),
                built.template.joint_paths))
            for placement in sorted(plan.placements,
                    key=lambda row: paths[row.fit_joint].count('|')):
                joined.set_name_matcher_fit_world_position(
                    paths[placement.fit_joint], placement.world_position)
            OrientFitJoints(joined).apply(
                body_with_hand_orientation_request(), container)
            for placement in plan.placements:
                actual = joined.capture_name_matcher_fit_world_position(
                    paths[placement.fit_joint])
                if any(abs(a-b)>1e-4 for a,b in zip(
                        actual, placement.world_position)):
                    raise RuntimeError('NameMatcher Fit 放置读回不一致：'
                                       + placement.fit_joint)
            if host.capture_source_skeleton(current_root) != current_source:
                raise RuntimeError('NameMatcher 修改了来源骨架')
            if (host.capture_name_matcher_skin_boundary(current_root)
                    != skin_boundary):
                raise RuntimeError('NameMatcher Fit 创建改变了来源 Skin')
        return NameMatcherFitResult(len(plan.placements),
                                    plan.missing, plan.scale,
                                    current_root)
