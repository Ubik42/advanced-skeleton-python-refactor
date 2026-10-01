"""Retain a saved source Spline layout during same-character rebuilding.

The saved graph controls its own count and spaces. Recreating it from a newer
Fit label-count algorithm would reinterpret the existing animation channels.
Changing authored topology is a separate migration, never a silent rebuild.
"""
from dataclasses import replace
from .body_spline import BodySplinePlan
from .fit_settings import FitSkeletonValidationError


def source_spline_identity(paths):
    return tuple(path.rsplit('|',1)[-1].rsplit(':',1)[-1] for path in paths)


def saved_source_spline_layout(source_paths,layouts):
    if layouts is None:
        return None
    identity=source_spline_identity(source_paths)
    matches=[plan for plan in layouts if isinstance(plan,BodySplinePlan)
             and source_spline_identity(plan.body_joints)==identity]
    if len(matches)!=1:
        raise FitSkeletonValidationError('来源 Spline 重建的原始骨链身份不唯一或已改变')
    return matches[0]


def retain_source_spline_layout(plan,saved):
    if saved is None:
        return plan
    if (source_spline_identity(plan.body_joints)!=source_spline_identity(saved.body_joints)
            or plan.system_name!=saved.system_name
            or len(saved.targets)!=len(saved.positions)
            or len(saved.targets)<2):
        raise FitSkeletonValidationError('来源 Spline 保存布局与重建系统不一致')
    # Preserve every control-count-dependent graph branch, including older
    # graphs without fake-mid, Hybrid, controller layers or parent follow.
    fields=('targets','positions','use_offset_parent_matrix','even_stretch_graph',
        'twist_ramp_graph','mid_follow_graph','isolated_mid_follow_graph',
        'sub_targets','extra_curve','fk_root_point_from_receiver','source_curve_points',
        'fake_mid_control','source_hybrid_graph','source_control_axes','source_ik_local',
        'source_cv_axes','source_controller_layers','source_follow_parent','source_follow_targets',
        'source_fixed_orient_unique','source_first_translate','source_world_controls')
    return replace(plan,**{field:getattr(saved,field) for field in fields})
