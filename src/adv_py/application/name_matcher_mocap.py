"""Connect an already imported NameMatcher skeleton to ADV controls."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.name_matcher_fit import (
    NameMatcherRow, NameMatcherRules,
    plan_name_matcher_constraints)
from adv_py.core.name_matcher_mocap import plan_name_matcher_mocap


@dataclass(frozen=True, slots=True)
class NameMatcherMocapResult:
    connected_controls: int
    missing: tuple[str, ...]


class ConnectNameMatchedMocap:
    def __init__(self, host):
        self._host = host

    def apply(self, source_root: str, rows: tuple[NameMatcherRow, ...],
              rules: NameMatcherRules) -> NameMatcherMocapResult:
        host = self._host
        source = host.capture_source_skeleton(source_root)
        advanced = host.capture_name_matcher_advanced_joints()
        registration = host.read_character_registration()
        mapping = plan_name_matcher_constraints(advanced,
            tuple((joint.path, joint.name) for joint in source), rows, rules)
        plan = plan_name_matcher_mocap(mapping, registration)
        skin_boundary = host.capture_name_matcher_skin_boundary(source_root)
        host.preflight_name_matcher_mocap(plan)
        with host.transaction('NameMatcher 动捕连接'):
            if (host.capture_source_skeleton(source_root) != source
                    or host.capture_name_matcher_advanced_joints()
                    != advanced
                    or host.read_character_registration() != registration
                    or host.capture_name_matcher_skin_boundary(source_root)
                    != skin_boundary):
                raise FitSkeletonValidationError(
                    'NameMatcher 动捕来源或角色在执行前变化')
            created = host.apply_name_matcher_mocap(plan)
            host.verify_name_matcher_mocap(plan, created)
            if host.capture_name_matcher_skin_boundary(source_root) != skin_boundary:
                raise RuntimeError('NameMatcher 动捕连接改变了来源 Skin')
        return NameMatcherMocapResult(len(plan.links) + len(plan.poles),
            tuple(sorted(set(mapping.missing)
                         | set(plan.unmapped_controls))))
