"""Build ADV Body and attach an imported skinned skeleton in one undo chunk."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.name_matcher_fit import (
    NameMatcherRow, NameMatcherRules, plan_name_matcher_constraints)

from .name_matcher_fit import BuildNameMatchedFit, NameMatcherFitResult
from .name_matcher_constraints import (
    ConnectNameMatchedSkeleton, NameMatcherConstraintResult)
from .name_matcher_animation import (
    BakeNameMatchedAnimation, NameMatcherAnimationBakeResult)
from .registered_body_build import (
    BuildRegisteredBodyCharacter, RegisteredBodyBuildResult,
    _JoinedTransactionHost)


@dataclass(frozen=True, slots=True)
class NameMatchedCharacterResult:
    fit: NameMatcherFitResult
    body: RegisteredBodyBuildResult
    attachment: NameMatcherConstraintResult
    animation: NameMatcherAnimationBakeResult | None
    skins_preserved: int


class BuildNameMatchedCharacter:
    """MEL AutoRig's Fit -> Body -> external Skin skeleton route."""

    def __init__(self, host):
        self._host = host

    def apply(self, source_root: str,
              rows: tuple[NameMatcherRow, ...],
              rules: NameMatcherRules) -> NameMatchedCharacterResult:
        host = self._host
        source = host.capture_source_skeleton(source_root)
        skin_boundary = host.capture_name_matcher_skin_boundary(source_root)
        animation = host.capture_name_matcher_source_animation(source_root)
        with host.transaction('NameMatcher 创建角色并连接来源 Skin 骨架'):
            if (host.capture_source_skeleton(source_root) != source
                    or host.capture_name_matcher_skin_boundary(source_root)
                    != skin_boundary
                    or host.capture_name_matcher_source_animation(source_root)
                    != animation):
                raise FitSkeletonValidationError(
                    'NameMatcher 来源在构建前变化')
            joined = _JoinedTransactionHost(host)
            if animation:
                joined.keep_name_matcher_source_animation(
                    source_root, animation)
            fit = BuildNameMatchedFit(joined).apply(
                source_root, rows, rules)
            scene_before = host.capture_body_scene_nodes()
            body = BuildRegisteredBodyCharacter(joined).apply(
                'FitSkeleton', _scene_before=scene_before)
            current_source = host.capture_source_skeleton(fit.source_root)
            mapping = plan_name_matcher_constraints(
                host.capture_name_matcher_advanced_joints(),
                tuple((joint.path, joint.name)
                      for joint in current_source), rows, rules)
            if not any(pair.external_joint == current_source[0].path
                    and pair.advanced_joint.rsplit('|', 1)[-1]
                        .rsplit(':', 1)[-1] == 'Root_M'
                    for pair in mapping.pairs):
                raise FitSkeletonValidationError(
                    'NameMatcher 自动构建必须映射来源根到 Body Root_M')
            attachment = ConnectNameMatchedSkeleton(joined).apply(
                fit.source_root, rows, rules)
            baked = (BakeNameMatchedAnimation(joined).apply(
                fit.source_root, rows, rules) if animation else None)
            if (host.capture_name_matcher_skin_boundary(fit.source_root)
                    != skin_boundary):
                raise RuntimeError(
                    'NameMatcher 自动构建改变了来源 Skin 或模型身份')
        return NameMatchedCharacterResult(
            fit, body, attachment, baked, len(skin_boundary))
