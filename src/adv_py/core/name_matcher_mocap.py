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
    unmapped_controls: tuple[str, ...]


def plan_name_matcher_mocap(mapping: NameMatcherConstraintPlan,
        registration: CharacterRegistration) -> NameMatcherMocapPlan:
    """Mirror MEL's FK, Root, wrist/ankle IK and toe-control branches."""
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
    for pair in mapping.pairs:
        leaf = pair.advanced_joint.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        base, separator, side = leaf.rpartition('_')
        if separator != '_' or side not in ('R', 'L', 'M'):
            continue
        if leaf == 'Root_M':
            root = control('root.x')
            if root:
                links.append(NameMatcherMocapLink(
                    pair.external_joint, root, True, True))
            else:
                missing.append('root.x')
            continue
        fk = control(
            'torso.Torso' + leaf + 'FK',
            'arm.fk.' + base + 'FK_' + side,
            'leg.fk.' + base + 'FK_' + side,
            'hand.fk.' + base + 'FK_' + side)
        if fk:
            links.append(NameMatcherMocapLink(
                pair.external_joint, fk, False, True))
        else:
            missing.append(leaf)
        if base in ('Wrist', 'Ankle') and side in ('R', 'L'):
            key = ('arm' if base == 'Wrist' else 'leg') + '.ik.' + side
            target = control(key)
            if target:
                links.append(NameMatcherMocapLink(
                    pair.external_joint, target, True, True))
            else:
                missing.append(key)
        if base == 'Toes' and side in ('R', 'L'):
            key = 'foot.toe.' + side
            target = control(key)
            if target:
                links.append(NameMatcherMocapLink(
                    pair.external_joint, target, False, True))
        if base in ('Elbow', 'Knee') and side in ('R', 'L'):
            limb = 'arm' if base == 'Elbow' else 'leg'
            key = limb + '.pole.' + side
            target = control(key)
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
        tuple(sorted(set(missing))))
