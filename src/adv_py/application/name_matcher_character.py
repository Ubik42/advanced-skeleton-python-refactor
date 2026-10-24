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
              rules: NameMatcherRules, *, template_name=None, preparation=None) -> NameMatchedCharacterResult:
        host = self._host
        native_fit = callable(getattr(host,'create_source_name_matched_fit',None))
        source_reader=(getattr(host,'capture_source_name_matcher_character_boundary',None)
                       if native_fit else host.capture_source_skeleton)
        if not callable(source_reader):
            raise FitSkeletonValidationError('原版 NameMatcher 创建角色缺少实际来源对象边界')
        source = source_reader(source_root)
        skin_boundary = host.capture_name_matcher_skin_boundary(source_root)
        animation = host.capture_name_matcher_source_animation(source_root)
        with host.transaction('NameMatcher 创建角色并连接来源 Skin 骨架'):
            if (source_reader(source_root) != source
                    or host.capture_name_matcher_skin_boundary(source_root)
                    != skin_boundary
                    or host.capture_name_matcher_source_animation(source_root)
                    != animation):
                raise FitSkeletonValidationError(
                    'NameMatcher 来源在构建前变化')
            joined = _JoinedTransactionHost(host)
            native_fit = callable(getattr(joined,'create_source_name_matched_fit',None))
            if animation and not native_fit:
                joined.keep_name_matcher_source_animation(
                    source_root, animation)
            fit = BuildNameMatchedFit(joined).apply(
                source_root, rows, rules,template_name=template_name,preparation=preparation)
            if native_fit:
                animation = joined.capture_name_matcher_source_animation(fit.source_root)
                if animation:
                    clone,_count=joined.keep_name_matcher_source_animation(fit.source_root,animation)
                    if not clone:animation=()
            scene_before = host.capture_body_scene_nodes()
            body = BuildRegisteredBodyCharacter(joined).apply(
                'FitSkeleton', _scene_before=scene_before)
            if not native_fit:
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
            native_attach = getattr(joined,'attach_source_name_matcher_skeleton',None)
            if callable(native_attach):
                joined.create_source_name_matcher_blend_controls()
                attachment = native_attach(fit.source_root,rows,rules)
            else:
                attachment = ConnectNameMatchedSkeleton(joined).apply(
                    fit.source_root, rows, rules)
            baked = (BakeNameMatchedAnimation(joined).apply(
                fit.source_root, rows, rules) if animation else None)
            if (host.capture_name_matcher_skin_boundary(fit.source_root)
                    != skin_boundary):
                raise RuntimeError(
                    'NameMatcher 自动构建改变了来源 Skin 或模型身份')
            if native_fit:
                joined.auto_scale_source_name_matcher_fk_curves()
                from dataclasses import replace
                body = replace(body,registration=joined.read_character_registration())
        return NameMatchedCharacterResult(
            fit, body, attachment, baked, len(skin_boundary))
