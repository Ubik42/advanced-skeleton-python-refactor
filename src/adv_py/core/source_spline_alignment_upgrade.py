"""Explicit migration of saved Spline reference frames through bind rebuilding.

Only the missing native AlignIKTo feature is enabled. Existing control counts,
axes, mode ranges and solver branches remain the saved layout's decisions.
The replacement builder creates reference nodes in its actual bind pose; the
animated source scene is never used as an inferred FKX bind matrix.
"""
from dataclasses import replace

from .body_spline import BodySplinePlan
from .character_registry import CharacterRegistryError, is_source_body_registration


def source_spline_alignment_upgrade_systems(registration, systems=None):
    if not is_source_body_registration(registration):
        raise CharacterRegistryError('AlignIKTo 升级需要已登记的原版来源 Body')
    layouts = tuple(plan for plan in (registration.spine, *registration.additional_spines)
                    if isinstance(plan, BodySplinePlan))
    available = {plan.system_name: plan for plan in layouts}
    if len(available) != len(layouts):
        raise CharacterRegistryError('Spline 保存系统身份重复')
    if systems is None:
        selected = tuple(plan.system_name for plan in layouts
                         if plan.source_curve_points and not plan.source_alignment_frames)
    else:
        if (not isinstance(systems, (tuple, list))
                or any(not isinstance(name, str) for name in systems)
                or len(set(systems)) != len(systems)
                or set(systems) - available.keys()):
            raise CharacterRegistryError('AlignIKTo 升级必须明确指定现有且不重复的 Spline 系统')
        selected = tuple(systems)
    for system in selected:
        if not available[system].source_curve_points:
            raise CharacterRegistryError('AlignIKTo 升级只适用于原版来源 Spline：'+system)
    return tuple(system for system in selected if not available[system].source_alignment_frames)


def upgrade_source_spline_alignment_layouts(layouts, systems):
    """Return a feature policy, leaving the original registration untouched."""
    if (not isinstance(systems, (tuple, list))
            or any(not isinstance(name, str) for name in systems)
            or len(set(systems)) != len(systems)):
        raise CharacterRegistryError('AlignIKTo 升级系统列表无效')
    if layouts is None:
        raise CharacterRegistryError('AlignIKTo 升级缺少已捕获的原版 Spline 布局')
    available = {plan.system_name: plan for plan in layouts if isinstance(plan, BodySplinePlan)}
    if len(available) != len(layouts) or set(systems) - available.keys():
        raise CharacterRegistryError('AlignIKTo 升级与保存的 Spline 布局不一致')
    selected = frozenset(systems)
    if any(not available[name].source_curve_points for name in selected):
        raise CharacterRegistryError('AlignIKTo 升级不能改变非来源 Spline 的求解图')
    return tuple(replace(plan, source_alignment_frames=True)
                 if plan.system_name in selected else plan for plan in layouts)


def audit_source_spline_alignment_upgrade(before, after, systems):
    """A reference-frame migration cannot silently upgrade other old features."""
    old = {plan.system_name: plan for plan in (before.spine, *before.additional_spines)
           if isinstance(plan, BodySplinePlan)}
    new = {plan.system_name: plan for plan in (after.spine, *after.additional_spines)
           if isinstance(plan, BodySplinePlan)}
    if old.keys() != new.keys() or set(systems) - old.keys():
        raise CharacterRegistryError('AlignIKTo 升级改变了 Spline 系统集合')
    retained = ('targets', 'positions', 'sub_targets', 'extra_curve',
        'use_offset_parent_matrix', 'source_mode', 'source_control_axes',
        'source_cv_axes', 'source_ik_local', 'source_world_controls',
        'source_controller_layers', 'source_hybrid_graph', 'source_native_follow',
        'source_follow_parent', 'source_follow_targets', 'fake_mid_control',
        'source_first_translate', 'source_start_volume', 'even_stretch_graph',
        'twist_ramp_graph', 'mid_follow_graph', 'isolated_mid_follow_graph',
        'fk_root_point_from_receiver', 'source_fixed_orient_unique')
    for system, left in old.items():
        right = new[system]
        if (any(getattr(left, field) != getattr(right, field) for field in retained)
                or right.source_alignment_frames != (
                    True if system in systems else left.source_alignment_frames)):
            raise CharacterRegistryError('AlignIKTo 升级改变了其他保存布局：'+system)
    from .character_preservation import validate_rebuild_layout
    validate_rebuild_layout(before, after)
