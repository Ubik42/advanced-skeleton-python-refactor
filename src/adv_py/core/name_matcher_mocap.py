"""Map NameMatcher's live MoCap skeleton onto registered ADV controls."""
from __future__ import annotations

from dataclasses import dataclass

from .character_registry import CharacterRegistration
from .fit_settings import FitSkeletonValidationError
from .name_matcher_fit import NameMatcherConstraintPlan
from .source_control_identity import source_control_roles, source_leaf


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
    source_joint: str | None = None


@dataclass(frozen=True, slots=True)
class NameMatcherMocapPlan:
    links: tuple[NameMatcherMocapLink, ...]
    poles: tuple[NameMatcherPoleLink, ...]
    root_control: str | None
    spine_control: str | None
    use_extra: bool
    unmapped_controls: tuple[str, ...]
    # Original per-DeformationSystem-joint command order, including Pole
    # helpers interleaved with FK/IK output constraints.
    operations: tuple[tuple[str, int], ...] = ()


def plan_name_matcher_mocap(mapping: NameMatcherConstraintPlan,
        registration: CharacterRegistration,
        *, use_extra: bool = False, allow_empty: bool = False) -> NameMatcherMocapPlan:
    """Mirror MEL's FK, Root, wrist/ankle IK and toe-control branches."""
    if type(use_extra) is not bool or type(allow_empty) is not bool:
        raise FitSkeletonValidationError('NameMatcher Extra 选项无效')
    controls: dict[str, set[str]] = {}
    roles = source_control_roles(registration)
    role_controls: dict[str, set[str]] = {}
    for channel in registration.channels:
        role = roles.get(source_leaf(channel.node))
        if role:
            role_controls.setdefault(role, set()).add(channel.node)
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

    def original(role, *legacy_keys):
        matches = role_controls.get(role, set())
        if len(matches) > 1:
            raise FitSkeletonValidationError('NameMatcher 原版控制器身份不唯一：' + role)
        return next(iter(matches)) if matches else control(*legacy_keys)

    links = []
    poles = []
    operations = []
    def add_link(link):
        operations.append(('link',len(links)))
        links.append(link)
    def add_pole(pole):
        operations.append(('pole',len(poles)))
        poles.append(pole)
    missing = []
    suffix = '.extra' if use_extra else ''
    spine_control = original('IKExtraSpine3_M' if use_extra else 'IKSpine3_M',
                             'spine.ik' + suffix)
    # Native asMappingUIFunction addresses IKSpine3_M literally. Resolve
    # that source end role only; other custom splines are not substituted.
    for pair in mapping.pairs:
        leaf = pair.advanced_joint.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        base, separator, side = leaf.rpartition('_')
        if separator != '_' or side not in ('R', 'L', 'M'):
            continue
        if leaf == 'Root_M':
            root = original('RootExtraX_M' if use_extra else 'RootX_M', 'root.x' + suffix)
            if root:
                add_link(NameMatcherMocapLink(
                    pair.external_joint, root, True, True))
            else:
                missing.append('root.x')
            continue
        fk = original(('FKExtra' if use_extra else 'FK') + leaf,
            'torso.Torso' + leaf + 'FK' + suffix,
            'arm.fk.' + base + 'FK_' + side + suffix,
            'leg.fk.' + base + 'FK_' + side + suffix,
            'hand.fk.' + base + 'FK_' + side + suffix)
        if fk:
            add_link(NameMatcherMocapLink(
                pair.external_joint, fk, False, True))
        else:
            missing.append(leaf)
            if registration.source_limbs or any(channel.key.startswith('generic.fk.')
                                                 for channel in registration.channels):
                # Native continues before its IK branches when this joint
                # has no FK/FKExtra receiving control.
                continue
        if base in ('Wrist', 'Ankle') and side in ('R', 'L'):
            key = ('arm' if base == 'Wrist' else 'leg') + '.ik.' + side
            target = original('IK' + ('Extra' if use_extra else '')
                + ('Arm' if base == 'Wrist' else 'Leg') + '_' + side,
                key if not use_extra else
                ('arm' if base == 'Wrist' else 'leg')
                + '.ik.extra.' + side)
            if target:
                add_link(NameMatcherMocapLink(
                    pair.external_joint, target, True, True))
            else:
                missing.append(key)
        if base == 'Toes' and side in ('R', 'L'):
            key = 'foot.toe.' + side
            target = original(('IKExtra' if use_extra else 'IK') + 'Toes_' + side,
                key if not use_extra else
                             'foot.toe.extra.' + side)
            if target:
                add_link(NameMatcherMocapLink(
                    pair.external_joint, target, False, True))
        if leaf == 'Chest_M' and spine_control:
            add_link(NameMatcherMocapLink(
                pair.external_joint, spine_control, True, True))
        if base in ('Elbow', 'Knee') and side in ('R', 'L'):
            limb = 'arm' if base == 'Elbow' else 'leg'
            key = limb + '.pole.' + side
            target = original('Pole' + ('Extra' if use_extra else '')
                + ('Arm' if base == 'Elbow' else 'Leg') + '_' + side,
                key if not use_extra else
                             limb + '.pole.extra.' + side)
            if target:
                add_pole(NameMatcherPoleLink(
                    pair.external_joint, target, limb,pair.advanced_joint))
            else:
                missing.append(key)
    if not links and not allow_empty:
        raise FitSkeletonValidationError(
            'NameMatcher 没有可接收动捕的已登记控制器')
    if len({link.control for link in links}) != len(links):
        raise FitSkeletonValidationError(
            'NameMatcher 动捕控制器被多个来源关节重复驱动')
    if len({pole.control for pole in poles}) != len(poles):
        raise FitSkeletonValidationError(
            'NameMatcher Pole Vector 控制器被重复驱动')
    return NameMatcherMocapPlan(
        tuple(links), tuple(poles), original('RootX_M', 'root.x'),
        spine_control, use_extra,
        tuple(sorted(set(missing))),tuple(operations))


def source_mocap_operations(plan):
    expected = {('link',index) for index in range(len(plan.links))}
    expected.update(('pole',index) for index in range(len(plan.poles)))
    operations = plan.operations or tuple(
        [('link',index) for index in range(len(plan.links))]
        + [('pole',index) for index in range(len(plan.poles))])
    if (any(not isinstance(row,tuple) or len(row)!=2
            or row[0] not in ('link','pole') or type(row[1]) is not int
            for row in operations)
            or len(operations)!=len(expected) or set(operations)!=expected):
        raise FitSkeletonValidationError('NameMatcher 原版动捕操作顺序不完整')
    return operations
