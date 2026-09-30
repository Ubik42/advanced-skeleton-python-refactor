"""Constrain an imported skinned skeleton to the ADV deformation joints."""
from __future__ import annotations

from dataclasses import dataclass

from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.name_matcher_fit import (
    NameMatcherRow, NameMatcherRules,
    plan_name_matcher_constraints)


@dataclass(frozen=True, slots=True)
class NameMatcherConstraintResult:
    connected: int
    missing: tuple[str, ...]


class ConnectNameMatchedSkeleton:
    def __init__(self, host):
        self._host = host

    def apply(self, source_root: str, rows: tuple[NameMatcherRow, ...],
              rules: NameMatcherRules) -> NameMatcherConstraintResult:
        host = self._host
        source = host.capture_source_skeleton(source_root)
        advanced = host.capture_name_matcher_advanced_joints()
        plan = plan_name_matcher_constraints(advanced,
            tuple((joint.path, joint.name) for joint in source),
            rows, rules)
        skin_boundary = host.capture_name_matcher_skin_boundary(source_root)
        host.preflight_name_matcher_constraints(plan)
        with host.transaction('NameMatcher 外部骨架跟随 Body'):
            if (host.capture_source_skeleton(source_root) != source
                    or host.capture_name_matcher_advanced_joints()
                    != advanced
                    or host.capture_name_matcher_skin_boundary(source_root)
                    != skin_boundary):
                raise FitSkeletonValidationError(
                    'NameMatcher 来源或 Body 骨架在执行前发生变化')
            created = host.apply_name_matcher_constraints(plan)
            host.verify_name_matcher_constraints(plan, created)
            if host.capture_name_matcher_skin_boundary(source_root) != skin_boundary:
                raise RuntimeError('NameMatcher 约束改变了原 Skin 连接')
        return NameMatcherConstraintResult(len(plan.pairs), plan.missing)


@dataclass(frozen=True, slots=True)
class NameMatcherSkinTransferResult:
    skins: int
    matrix_links: int
    retained_branches: int
    preserved_transforms: int
    missing: tuple[str, ...]


class TransferNameMatchedSkinInfluences:
    """MEL AutoRigTransferSkinning: rewire matrix inputs, retain Skin data."""

    def __init__(self, host):
        self._host = host

    def apply(self, source_root: str, rows: tuple[NameMatcherRow, ...],
              rules: NameMatcherRules) -> NameMatcherSkinTransferResult:
        host = self._host
        source = host.capture_source_skeleton(source_root)
        advanced = host.capture_name_matcher_advanced_joints()
        plan = plan_name_matcher_constraints(advanced,
            tuple((joint.path, joint.name) for joint in source), rows, rules)
        links = host.capture_name_matcher_skin_links(plan)
        handoff = host.capture_name_matcher_source_handoff(
            source, plan, links)
        payload = host.capture_name_matcher_skin_payload(links)
        with host.transaction('NameMatcher Skin 影响关节转接'):
            if (host.capture_source_skeleton(source_root) != source
                    or host.capture_name_matcher_advanced_joints()
                    != advanced
                    or host.capture_name_matcher_skin_links(plan) != links
                    or host.capture_name_matcher_source_handoff(
                        source, plan, links) != handoff
                    or host.capture_name_matcher_skin_payload(links)
                    != payload):
                raise FitSkeletonValidationError(
                    'NameMatcher Skin 来源或 Body 骨架在执行前变化')
            host.apply_name_matcher_skin_links(links)
            host.verify_name_matcher_skin_links(links)
            retained, geometry = host.apply_name_matcher_source_handoff(
                handoff)
            host.normalize_name_matcher_skins(links)
            host.verify_name_matcher_skin_links(links)
            host.verify_name_matcher_skin_payload(payload,
                host.capture_name_matcher_skin_payload(links))
        return NameMatcherSkinTransferResult(
            len({link.skin_uuid for link in links}),
            len(links), retained, geometry, plan.missing)
