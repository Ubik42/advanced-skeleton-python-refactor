"""ADV NameMatcher's editable joint-name rows and side naming rules."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re

from .fit_settings import FitSkeletonValidationError
from .fit_template import FitTemplateSpec


@dataclass(frozen=True, slots=True)
class NameMatcherRules:
    right: str = "R"
    left: str = "L"
    middle: str = ""
    side_before_name: bool = False
    side_underscore: bool = False


@dataclass(frozen=True, slots=True)
class NameMatcherRow:
    fit_joint: str
    source_base: str


@dataclass(frozen=True, slots=True)
class NameMatcherPlacement:
    fit_joint: str
    source_path: str
    world_position: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class NameMatcherFitPlan:
    placements: tuple[NameMatcherPlacement, ...]
    missing: tuple[str, ...]
    scale: float


@dataclass(frozen=True, slots=True)
class NameMatcherConstraintPair:
    advanced_joint: str
    external_joint: str


@dataclass(frozen=True, slots=True)
class NameMatcherConstraintPlan:
    pairs: tuple[NameMatcherConstraintPair, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NameMatcherSkinMatrixLink:
    advanced_joint: str
    external_joint: str
    destination: str
    original_source: str
    bind_pre_matrix: tuple[float, ...]
    bind_pre_source: str | None
    skin_uuid: str


def _external_name(base: str, side: str, rules: NameMatcherRules) -> str:
    divider = "_" if rules.side_underscore and side else ""
    return (side + divider + base if rules.side_before_name
            else base + divider + side)


def _fit_template_name(name: str) -> str:
    finger = re.fullmatch(
        r'(Thumb|Index|Middle|Ring|Pinky)Finger([1-4])', name)
    if finger is not None:
        return finger.group(1) + (
            'End' if finger.group(2) == '4' else finger.group(2))
    return name


def plan_name_matcher_fit(template: FitTemplateSpec,
        source: tuple[tuple[str, str, tuple[float, float, float]], ...],
        rows: tuple[NameMatcherRow, ...], rules: NameMatcherRules,
        *, up_axis: str) -> NameMatcherFitPlan:
    if (not isinstance(rules, NameMatcherRules)
            or up_axis not in ("y", "z")
            or any(not isinstance(side, str) for side in
                (rules.right, rules.left, rules.middle))
            or any('|' in side or ':' in side for side in
                (rules.right, rules.left, rules.middle))
            or type(rules.side_before_name) is not bool
            or type(rules.side_underscore) is not bool
            or not rows or any(not isinstance(row, NameMatcherRow)
                or not row.fit_joint or not row.source_base
                or any(character in row.source_base for character in '|:')
                for row in rows)):
        raise FitSkeletonValidationError("NameMatcher 映射或场景 Up Axis 无效")
    if len({_fit_template_name(row.fit_joint) for row in rows}) != len(rows):
        raise FitSkeletonValidationError("NameMatcher Fit 名称重复")
    by_fit = {joint.name: joint for joint in template.joints}
    if any(_fit_template_name(row.fit_joint) not in by_fit for row in rows):
        raise FitSkeletonValidationError("NameMatcher 映射引用模板以外的 Fit 关节")
    by_leaf: dict[str, list[tuple[str, tuple[float, float, float]]]] = {}
    for path, name, position in source:
        if (not path or not name or len(position) != 3
                or any(not isfinite(float(value)) for value in position)):
            raise FitSkeletonValidationError("NameMatcher 来源关节无效")
        by_leaf.setdefault(name.rsplit(':', 1)[-1], []).append((path, position))
    if len({path for path, _, _ in source}) != len(source):
        raise FitSkeletonValidationError("NameMatcher 来源关节路径重复")
    axis = 1 if up_axis == "y" else 2
    height = max((position[axis] for _, _, position in source), default=0.)
    if height <= 0.:
        raise FitSkeletonValidationError("NameMatcher 来源骨架高度无效")
    # MEL detects a middle Fit joint from its template's world X location.
    x_positions: dict[str, float] = {}
    for joint in template.joints:
        parent_x = x_positions.get(joint.parent, 0.)
        x_positions[joint.name] = parent_x + joint.local_position[0]
    placements = []
    missing = []
    for row in rows:
        fit_name = _fit_template_name(row.fit_joint)
        middle = abs(x_positions[fit_name]) <= 0.001
        side = rules.middle if middle else rules.right
        name = _external_name(row.source_base, side, rules)
        candidates = by_leaf.get(name, ())
        if len(candidates) > 1:
            raise FitSkeletonValidationError(
                "NameMatcher 来源关节名称不唯一：" + name)
        if not candidates:
            missing.append(name)
            continue
        path, position = candidates[0]
        placements.append(NameMatcherPlacement(
            fit_name, path, position))
    if not placements:
        raise FitSkeletonValidationError("NameMatcher 没有匹配到任何来源关节")
    if len({row.source_path for row in placements}) != len(placements):
        raise FitSkeletonValidationError("NameMatcher 一个来源关节被重复映射")
    return NameMatcherFitPlan(tuple(placements), tuple(missing), height / 17.)


def plan_name_matcher_constraints(
        advanced_joints: tuple[str, ...],
        external_joints: tuple[tuple[str, str], ...],
        rows: tuple[NameMatcherRow, ...], rules: NameMatcherRules,
        ) -> NameMatcherConstraintPlan:
    """Map DeformationSystem's _R/_L/_M joints like AutoRigConstraint."""
    if not advanced_joints or not rows or not isinstance(rules, NameMatcherRules):
        raise FitSkeletonValidationError('NameMatcher 约束缺少骨架或映射')
    by_fit = {_fit_template_name(row.fit_joint): row.source_base
              for row in rows}
    if len(by_fit) != len(rows):
        raise FitSkeletonValidationError('NameMatcher 约束 Fit 映射重复')
    by_external: dict[str, list[str]] = {}
    for path, name in external_joints:
        if not path or not name:
            raise FitSkeletonValidationError('NameMatcher 外部关节无效')
        by_external.setdefault(name.rsplit(':', 1)[-1], []).append(path)
    pairs = []
    missing = []
    for advanced in advanced_joints:
        leaf = advanced.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        base, separator, side = leaf.rpartition('_')
        if separator != '_' or side not in ('R', 'L', 'M'):
            continue
        mapped = by_fit.get(_fit_template_name(base))
        if mapped is None:
            continue
        marker = {'R': rules.right, 'L': rules.left,
                  'M': rules.middle}[side]
        external_name = _external_name(mapped, marker, rules)
        candidates = by_external.get(external_name, ())
        if len(candidates) > 1:
            raise FitSkeletonValidationError(
                'NameMatcher 外部关节名称不唯一：' + external_name)
        if not candidates:
            missing.append(external_name)
            continue
        pairs.append(NameMatcherConstraintPair(advanced, candidates[0]))
    if not pairs:
        raise FitSkeletonValidationError('NameMatcher 没有可连接的变形关节')
    if (len({row.advanced_joint for row in pairs}) != len(pairs)
            or len({row.external_joint for row in pairs}) != len(pairs)):
        raise FitSkeletonValidationError('NameMatcher 约束关节映射不是一对一')
    return NameMatcherConstraintPlan(tuple(pairs), tuple(sorted(set(missing))))
