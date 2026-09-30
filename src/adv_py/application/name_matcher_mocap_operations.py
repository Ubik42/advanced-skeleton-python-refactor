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
              rules: NameMatcherRules) -> NameMatcherZeroOutResult:
        host = self._host
        source = host.capture_source_skeleton(source_root)
        advanced = host.capture_name_matcher_advanced_joints()
        mapping = plan_name_matcher_constraints(advanced,
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
        session = host.capture_name_matcher_mocap_session()
        with host.transaction('NameMatcher 断开动捕骨架'):
            if host.capture_name_matcher_mocap_session() != session:
                raise FitSkeletonValidationError(
                    'NameMatcher 动捕连接在执行前变化')
            host.disconnect_name_matcher_mocap(session)
        return len(session.constraints)
