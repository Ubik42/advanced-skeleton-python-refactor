"""Plan original NameMatcher KeepAnimation -> FK control baking."""
from __future__ import annotations

from dataclasses import dataclass

from .character_registry import CharacterRegistration
from .fit_settings import FitSkeletonValidationError
from .name_matcher_fit import NameMatcherConstraintPlan
from .source_control_identity import source_fk_bindings


@dataclass(frozen=True, slots=True)
class NameMatcherAnimationLink:
    cloned_joint: str
    control: str


@dataclass(frozen=True, slots=True)
class NameMatcherAnimationBakePlan:
    links: tuple[NameMatcherAnimationLink, ...]
    fk_mode_plugs: tuple[str, ...]
    missing: tuple[str, ...]


def plan_name_matcher_animation_bake(
        mapping: NameMatcherConstraintPlan,
        registration: CharacterRegistration,
        clone_joints: tuple[str, ...]) -> NameMatcherAnimationBakePlan:
    controls: dict[str, set[str]] = {}
    source_controls: dict[str, set[str]] = {}
    for joint, control in source_fk_bindings(registration):
        source_controls.setdefault(joint, set()).add(control)
    for channel in registration.channels:
        stem, _, attribute = channel.key.rpartition('.')
        if attribute == 'rotateX':
            controls.setdefault(stem, set()).add(channel.node)
    clones: dict[str, list[str]] = {}
    for path in clone_joints:
        clones.setdefault(path.rsplit('|', 1)[-1].rsplit(':', 1)[-1],
                          []).append(path)
    links = []
    missing = []
    for pair in mapping.pairs:
        source_leaf = pair.external_joint.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        matches = clones.get(source_leaf, ())
        if len(matches) > 1:
            raise FitSkeletonValidationError(
                'NameMatcher 保留动画关节名称不唯一：' + source_leaf)
        if not matches:
            missing.append(source_leaf)
            continue
        leaf = pair.advanced_joint.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        base, separator, side = leaf.rpartition('_')
        if separator != '_' or side not in ('R', 'L', 'M'):
            continue
        keys = ('torso.Torso' + leaf + 'FK',
                'arm.fk.' + base + 'FK_' + side,
                'leg.fk.' + base + 'FK_' + side,
                'hand.fk.' + base + 'FK_' + side)
        control_paths = source_controls.get(leaf, set()) or set().union(
            *(controls.get(key, set()) for key in keys))
        if len(control_paths) > 1:
            raise FitSkeletonValidationError(
                'NameMatcher FK 动画控制器映射不唯一：' + leaf)
        if not control_paths:
            missing.append(leaf)
            continue
        links.append(NameMatcherAnimationLink(matches[0],
                                               next(iter(control_paths))))
    if not links or len({link.control for link in links}) != len(links):
        raise FitSkeletonValidationError(
            'NameMatcher 没有唯一的 FK 动画控制器映射')
    mode_keys = {limb.blend_key for limb in registration.source_limbs}
    spline_modes = {spline.mode_plug for spline in
                    (registration.spine, *registration.additional_spines)
                    if spline is not None and hasattr(spline, 'mode_plug')}
    fk_plugs = tuple(sorted({channel.node + '.' + channel.attribute
        for channel in registration.channels
        if channel.key in mode_keys
        or channel.node + '.' + channel.attribute in spline_modes
        or channel.attribute == 'FKIKBlend'
        or (channel.attribute == 'stabilize'
            and channel.node.rsplit('|', 1)[-1] == 'HipSwinger_M')
        or (channel.key.startswith(('arm.settings.', 'leg.settings.'))
            and channel.attribute.startswith(('ArmIkFk_', 'LegIkFk_')))
        or (channel.key.startswith(('spine.ik.', 'spine.spline.','source.spline.'))
            and channel.attribute in ('spineIkFk','FKIKBlend'))}))
    return NameMatcherAnimationBakePlan(
        tuple(links), fk_plugs, tuple(sorted(set(missing))))
