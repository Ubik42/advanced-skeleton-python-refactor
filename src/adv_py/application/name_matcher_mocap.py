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
              rules: NameMatcherRules, *,
              use_extra: bool = False, source_namespace: str | None = None) -> NameMatcherMocapResult:
        host = self._host
        native_mapping=getattr(host,'plan_source_name_matcher_mocap_mapping',None)
        boundary=getattr(host,'capture_source_name_matcher_mocap_boundary',None)
        if callable(native_mapping) and callable(boundary):
            return self._apply_native(source_root,rows,rules,use_extra,source_namespace)
        if source_namespace is not None:
            raise FitSkeletonValidationError('当前宿主没有原版按来源命名空间连接动捕的实现')
        source = host.capture_source_skeleton(source_root)
        advanced = host.capture_name_matcher_advanced_joints()
        registration = host.read_character_registration()
        planner = plan_name_matcher_constraints
        if callable(getattr(host, 'attach_source_name_matcher_skeleton', None)):
            from adv_py.core.source_name_matcher import plan_source_name_matcher_constraints
            planner = plan_source_name_matcher_constraints
        native_mapping=getattr(host,'plan_source_name_matcher_mocap_mapping',None)
        mapping = (native_mapping(source_root,rows,rules) if callable(native_mapping) else
            planner(advanced,tuple((joint.path,joint.name) for joint in source),rows,rules))
        plan = plan_name_matcher_mocap(mapping, registration,
                                      use_extra=use_extra)
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
            if callable(native_mapping) and native_mapping(source_root,rows,rules)!=mapping:
                raise FitSkeletonValidationError('NameMatcher 动捕原版名称解析在执行前变化')
            created = host.apply_name_matcher_mocap(plan)
            host.verify_name_matcher_mocap(plan, created)
            if host.capture_name_matcher_skin_boundary(source_root) != skin_boundary:
                raise RuntimeError('NameMatcher 动捕连接改变了来源 Skin')
        return NameMatcherMocapResult(len(plan.links) + len(plan.poles),
            tuple(sorted(set(mapping.missing)
                         | set(plan.unmapped_controls))))

    def _apply_native(self,source_root,rows,rules,use_extra,source_namespace):
        host=self._host
        options={} if source_namespace is None else dict(source_namespace=source_namespace)
        def mapping():
            return host.plan_source_name_matcher_mocap_mapping(source_root,rows,rules,**options)
        advanced=host.capture_name_matcher_advanced_joints()
        registration=host.read_character_registration()
        resolved=mapping()
        plan=plan_name_matcher_mocap(resolved,registration,use_extra=use_extra,allow_empty=True)
        boundary=host.capture_source_name_matcher_mocap_boundary(resolved)
        host.preflight_name_matcher_mocap(plan)
        with host.transaction('NameMatcher 原版按名称连接动捕'):
            if (mapping()!=resolved or host.capture_name_matcher_advanced_joints()!=advanced
                    or host.read_character_registration()!=registration
                    or host.capture_source_name_matcher_mocap_boundary(resolved)!=boundary):
                raise FitSkeletonValidationError('NameMatcher 动捕实际来源或角色在执行前变化')
            created=host.apply_name_matcher_mocap(plan)
            host.verify_name_matcher_mocap(plan,created)
            # Intentional Chest follow changes affect the evaluated pose.
            # Only Skin endpoints must stay identical after native Connect.
            if host.capture_source_name_matcher_mocap_boundary(resolved)[1]!=boundary[1]:
                raise RuntimeError('NameMatcher 动捕连接改变了生产 Skin 身份')
        return NameMatcherMocapResult(len(plan.links)+len(plan.poles),
            tuple(dict.fromkeys((*resolved.missing,*plan.unmapped_controls))))
