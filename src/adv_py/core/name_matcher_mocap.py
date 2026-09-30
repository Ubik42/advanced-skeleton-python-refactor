"""Map NameMatcher's live MoCap skeleton onto registered ADV controls."""
from __future__ import annotations

from dataclasses import dataclass

from .character_registry import CharacterRegistration
from .fit_settings import FitSkeletonValidationError
from .name_matcher_fit import NameMatcherConstraintPlan


@dataclass(frozen=True, slots=True)
class NameMatcherMocapLink:
    external_joint: str
    control: str
    point: bool
    orient: bool


@dataclass(frozen=True, slots=True)
class NameMatcherPoleLink:
    middle_joint: str
    control: str
    limb: str


@dataclass(frozen=True, slots=True)
class NameMatcherMocapPlan:
    links: tuple[NameMatcherMocapLink, ...]
    poles: tuple[NameMatcherPoleLink, ...]
    root_control: str | None
    spine_control: str | None
    use_extra: bool
    unmapped_controls: tuple[str, ...]


def plan_name_matcher_mocap(mapping: NameMatcherConstraintPlan,
        registration: CharacterRegistration,
        *, use_extra: bool = False) -> NameMatcherMocapPlan:
    """Mirror MEL's FK, Root, wrist/ankle IK and toe-control branches."""
    if type(use_extra) is not bool:
        raise FitSkeletonValidationError('NameMatcher Extra 选项无效')
    controls: dict[str, set[str]] = {}
    for channel in registration.channels:
        stem, _, attribute = channel.key.rpartition('.')
        if attribute in ('translateX', 'rotateX'):
            controls.setdefault(stem, set()).add(channel.node)

    def control(*keys: str) -> str | None:
        matches = set().union(*(controls.get(key, set()) for key in keys))
        if len(matches) > 1:
            raise FitSkeletonValidationError(
                'NameMatcher 多个控制器对应同一动捕语义：'
                + '、'.join(keys))
        return next(iter(matches)) if matches else None

    links = []
    poles = []
    missing = []
    suffix = '.extra' if use_extra else ''
    spine_control = control('spine.ik' + suffix)
    for pair in mapping.pairs:
        leaf = pair.advanced_joint.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        base, separator, side = leaf.rpartition('_')
        if separator != '_' or side not in ('R', 'L', 'M'):
            continue
        if leaf == 'Root_M':
            root = control('root.x' + suffix)
            if root:
                links.append(NameMatcherMocapLink(
                    pair.external_joint, root, True, True))
            else:
                missing.append('root.x')
            continue
        fk = control(
            'torso.Torso' + leaf + 'FK' + suffix,
            'arm.fk.' + base + 'FK_' + side + suffix,
            'leg.fk.' + base + 'FK_' + side + suffix,
            'hand.fk.' + base + 'FK_' + side + suffix)
        if fk:
            links.append(NameMatcherMocapLink(
                pair.external_joint, fk, False, True))
        else:
            missing.append(leaf)
        if base in ('Wrist', 'Ankle') and side in ('R', 'L'):
            key = ('arm' if base == 'Wrist' else 'leg') + '.ik.' + side
            target = control(key if not use_extra else
                ('arm' if base == 'Wrist' else 'leg')
                + '.ik.extra.' + side)
            if target:
                links.append(NameMatcherMocapLink(
                    pair.external_joint, target, True, True))
            else:
                missing.append(key)
        if base == 'Toes' and side in ('R', 'L'):
            key = 'foot.toe.' + side
            target = control(key if not use_extra else
                             'foot.toe.extra.' + side)
            if target:
                links.append(NameMatcherMocapLink(
                    pair.external_joint, target, False, True))
        if leaf == 'Chest_M' and spine_control:
            links.append(NameMatcherMocapLink(
                pair.external_joint, spine_control, True, True))
        if base in ('Elbow', 'Knee') and side in ('R', 'L'):
            limb = 'arm' if base == 'Elbow' else 'leg'
            key = limb + '.pole.' + side
            target = control(key if not use_extra else
                             limb + '.pole.extra.' + side)
            if target:
                poles.append(NameMatcherPoleLink(
                    pair.external_joint, target, limb))
            else:
                missing.append(key)
    if not links:
        raise FitSkeletonValidationError(
            'NameMatcher 没有可接收动捕的已登记控制器')
    if len({link.control for link in links}) != len(links):
        raise FitSkeletonValidationError(
            'NameMatcher 动捕控制器被多个来源关节重复驱动')
    if len({pole.control for pole in poles}) != len(poles):
        raise FitSkeletonValidationError(
            'NameMatcher Pole Vector 控制器被重复驱动')
    return NameMatcherMocapPlan(
        tuple(links), tuple(poles), control('root.x'),
        spine_control, use_extra,
        tuple(sorted(set(missing))))
