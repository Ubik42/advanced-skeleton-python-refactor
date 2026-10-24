"""MEL KeepAnimation and BakeFromKeepAnimationSkeleton orchestration."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.name_matcher_animation import (
    plan_name_matcher_animation_bake)
from adv_py.core.name_matcher_fit import (
    NameMatcherRow, NameMatcherRules, plan_name_matcher_constraints)


@dataclass(frozen=True, slots=True)
class NameMatcherKeptAnimationResult:
    clone_root: str
    animated_channels: int


@dataclass(frozen=True, slots=True)
class NameMatcherAnimationBakeResult:
    controls: int
    first_frame: float
    last_frame: float
    missing: tuple[str, ...]


class KeepNameMatchedAnimation:
    def __init__(self, host):
        self._host = host

    def apply(self, source_root: str) -> NameMatcherKeptAnimationResult:
        host = self._host
        native=getattr(host,'keep_source_name_matcher_animation',None)
        if callable(native):
            with host.transaction('NameMatcher 原版保留来源动画'):
                return native(source_root)
        source = host.capture_source_skeleton(source_root)
        skin = host.capture_name_matcher_skin_boundary(source_root)
        animation = host.capture_name_matcher_source_animation(source_root)
        if not animation:
            raise FitSkeletonValidationError(
                'NameMatcher 来源骨架没有直接动画曲线')
        with host.transaction('NameMatcher 保留来源动画骨架'):
            if (host.capture_source_skeleton(source_root) != source
                    or host.capture_name_matcher_skin_boundary(source_root)
                    != skin
                    or host.capture_name_matcher_source_animation(source_root)
                    != animation):
                raise FitSkeletonValidationError(
                    'NameMatcher 动画来源在复制前变化')
            clone, count = host.keep_name_matcher_source_animation(
                source_root, animation)
            if host.capture_name_matcher_skin_boundary(source_root) != skin:
                raise RuntimeError(
                    'NameMatcher 动画保留改变了来源 Skin')
        return NameMatcherKeptAnimationResult(clone, count)


class BakeNameMatchedAnimation:
    def __init__(self, host):
        self._host = host

    def apply(self, source_root: str, rows: tuple[NameMatcherRow, ...],
              rules: NameMatcherRules) -> NameMatcherAnimationBakeResult:
        host = self._host
        native=getattr(host,'bake_source_name_matcher_kept_animation',None)
        if callable(native):
            with host.transaction('NameMatcher 原版保留动画烘焙到 FK'):
                return native(source_root,rows,rules)
        session = host.capture_name_matcher_kept_animation()
        source = host.capture_source_skeleton(source_root)
        if source[0].path != session[1]:
            raise FitSkeletonValidationError(
                'NameMatcher 保留动画与当前来源根关节不对应')
        advanced = host.capture_name_matcher_advanced_joints()
        registration = host.read_character_registration()
        planner = plan_name_matcher_constraints
        if callable(getattr(host, 'attach_source_name_matcher_skeleton', None)):
            from adv_py.core.source_name_matcher import plan_source_name_matcher_constraints
            planner = plan_source_name_matcher_constraints
        mapping = planner(advanced,
            tuple((joint.path, joint.name) for joint in source),
            rows, rules)
        plan = plan_name_matcher_animation_bake(
            mapping, registration, session[3])
        skin = host.capture_name_matcher_skin_boundary(source_root)
        with host.transaction('NameMatcher 来源动画烘焙到 FK'):
            if (host.capture_name_matcher_kept_animation() != session
                    or host.capture_source_skeleton(source_root) != source
                    or host.capture_name_matcher_advanced_joints()
                    != advanced
                    or host.read_character_registration() != registration
                    or host.capture_name_matcher_skin_boundary(source_root)
                    != skin):
                raise FitSkeletonValidationError(
                    'NameMatcher 来源动画或角色在烘焙前变化')
            first, last = host.bake_name_matcher_kept_animation(
                plan, session)
            if host.capture_name_matcher_skin_boundary(source_root) != skin:
                raise RuntimeError(
                    'NameMatcher 动画烘焙改变了来源 Skin')
        return NameMatcherAnimationBakeResult(
            len(plan.links), first, last, plan.missing)
