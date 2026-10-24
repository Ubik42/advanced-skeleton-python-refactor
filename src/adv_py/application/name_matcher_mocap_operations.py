"""NameMatcher's source zeroing, control bake and connection removal."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.name_matcher_fit import (
    NameMatcherRow, NameMatcherRules, plan_name_matcher_constraints)


@dataclass(frozen=True, slots=True)
class NameMatcherZeroOutResult:
    joints: int
    missing: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NameMatcherBakeResult:
    controls: int
    first_frame: float
    last_frame: float


class ZeroOutNameMatchedMocap:
    def __init__(self, host):
        self._host = host

    def apply(self, source_root: str, rows: tuple[NameMatcherRow, ...],
              rules: NameMatcherRules, *,template_name=None,source_namespace=None) -> NameMatcherZeroOutResult:
        host = self._host
        native = getattr(host,'zero_out_source_name_matcher_joints',None)
        if callable(native):
            with host.transaction('NameMatcher 动捕关节旋转归零'):
                options={}
                if template_name is not None:options['template_name']=template_name
                if source_namespace is not None:options['source_namespace']=source_namespace
                return native(source_root,rows,rules,**options)
        if template_name is not None or source_namespace is not None:
            raise FitSkeletonValidationError('当前宿主没有原版动捕模板归零实现')
        source = host.capture_source_skeleton(source_root)
        advanced = host.capture_name_matcher_advanced_joints()
        planner = plan_name_matcher_constraints
        if callable(getattr(host, 'attach_source_name_matcher_skeleton', None)):
            from adv_py.core.source_name_matcher import plan_source_name_matcher_constraints
            planner = plan_source_name_matcher_constraints
        mapping = planner(advanced,
            tuple((joint.path, joint.name) for joint in source), rows, rules)
        skin_boundary = host.capture_name_matcher_skin_boundary(source_root)
        host.preflight_name_matcher_zero_out(mapping)
        with host.transaction('NameMatcher 动捕关节旋转归零'):
            if (host.capture_source_skeleton(source_root) != source
                    or host.capture_name_matcher_advanced_joints()
                    != advanced
                    or host.capture_name_matcher_skin_boundary(source_root)
                    != skin_boundary):
                raise FitSkeletonValidationError(
                    'NameMatcher Zero Out 来源在执行前变化')
            host.zero_out_name_matcher_joints(mapping)
            if host.capture_name_matcher_skin_boundary(source_root) != skin_boundary:
                raise RuntimeError('NameMatcher Zero Out 改变了来源 Skin')
        return NameMatcherZeroOutResult(
            len(mapping.pairs), mapping.missing)


class BakeNameMatchedMocap:
    def __init__(self, host):
        self._host = host

    def apply(self) -> NameMatcherBakeResult:
        host = self._host
        session = host.capture_name_matcher_mocap_session()
        with host.transaction('NameMatcher 动捕控制器烘焙'):
            if host.capture_name_matcher_mocap_session() != session:
                raise FitSkeletonValidationError(
                    'NameMatcher 动捕连接在执行前变化')
            first, last = host.bake_name_matcher_mocap(session)
        return NameMatcherBakeResult(len(session.controls), first, last)


class DisconnectNameMatchedMocap:
    def __init__(self, host):
        self._host = host

    def apply(self) -> int:
        host = self._host
        exists=getattr(host,'source_name_matcher_mocap_exists',None)
        if callable(exists) and not exists():
            # Original Disconnect is harmless when no MoCap group exists.
            return 0
        session = host.capture_name_matcher_mocap_session()
        with host.transaction('NameMatcher 断开动捕骨架'):
            if host.capture_name_matcher_mocap_session() != session:
                raise FitSkeletonValidationError(
                    'NameMatcher 动捕连接在执行前变化')
            host.disconnect_name_matcher_mocap(session)
        return len(session.constraints)
