"""Native NameMatcher configuration text and side-name arithmetic."""
from dataclasses import dataclass, replace
from .name_matcher_fit import (NameMatcherRow, NameMatcherRules,
                              NameMatcherConstraintPair, NameMatcherConstraintPlan)
from .fit_settings import FitSkeletonValidationError


@dataclass(frozen=True, slots=True)
class SourceNameMatcherTemplate:
    rows: tuple[NameMatcherRow, ...]
    rules: NameMatcherRules


def read_source_name_matcher_template(text):
    settings = {'sideRight':'Right','sideLeft':'Left','sideMiddle':'',
                'sideBeforeName':'1','sideUnderScore':'0'}
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        if '=' not in line:
            raise ValueError('NameMatcher 配置行缺少等号：'+line)
        name,value = line.split('=',1)
        name,value = name.strip(),value.strip()
        if name in settings:
            settings[name] = value
        elif name == 'www':
            continue
        else:
            rows.append(NameMatcherRow(name,value))
    if any(settings[key] not in ('0','1') for key in ('sideBeforeName','sideUnderScore')):
        raise ValueError('NameMatcher 侧别选项必须是 0 或 1')
    return SourceNameMatcherTemplate(tuple(rows),NameMatcherRules(
        settings['sideRight'],settings['sideLeft'],settings['sideMiddle'],
        settings['sideBeforeName']=='1',settings['sideUnderScore']=='1'))


def source_name_matcher_name(base, rules, *, middle=False, namespace=''):
    side = rules.middle if middle else rules.right
    separator = '_' if rules.side_underscore else ''
    # Unlike the generic planner, a blank RIGHT marker still gets '_'.
    # Source suppresses the separator only for an empty MIDDLE marker.
    if middle and not side:
        separator = ''
    leaf = side+separator+base if rules.side_before_name else base+separator+side
    return (namespace+':' if namespace else '')+leaf


def source_name_matcher_targets(advanced_joints, rows, rules, *, namespace=''):
    """Ordered aResolveds/bResolveds, including targets absent from the scene.

    The MEL adds these before checking existence. In particular Skin Transfer
    deletes the ancestor of the last resolved name, not the last existing pair.
    """
    by_fit = {row.fit_joint: row.source_base for row in rows}
    result = []
    for joint in advanced_joints:
        name = joint.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        if not name.endswith(('_R', '_L', '_M')) or name[:-2] not in by_fit:
            continue
        side = name[-1]
        target = source_name_matcher_name(by_fit[name[:-2]],
            replace(rules, right=rules.left) if side == 'L' else rules,
            middle=side == 'M', namespace=namespace)
        if target:
            result.append((joint, target))
    return tuple(result)


def plan_source_name_matcher_constraints(advanced_joints, external_joints, rows, rules):
    """asMappingUIFunction: exact Fit names, last matching row wins.

    Native templates include Finger0/Finger4 and intentionally repeated rows.
    Do not normalize these to the old synthetic Fit template's names.
    """
    by_fit = {row.fit_joint: row.source_base for row in rows}
    external = {}
    for path, name in external_joints:
        external.setdefault(name.rsplit(':', 1)[-1], []).append(path)
    pairs, missing = [], []
    for joint in advanced_joints:
        name = joint.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        if not name.endswith(('_R', '_L', '_M')):
            continue
        base, side = name[:-2], name[-1]
        if base not in by_fit:
            continue
        target = source_name_matcher_name(by_fit[base],
            replace(rules, right=rules.left) if side == 'L' else rules,
            middle=side == 'M')
        paths = external.get(target, ())
        if len(paths) > 1:
            raise FitSkeletonValidationError('NameMatcher 外部关节名称不唯一：' + target)
        if paths:
            pairs.append(NameMatcherConstraintPair(joint, paths[0]))
        else:
            missing.append(target)
    return NameMatcherConstraintPlan(tuple(pairs), tuple(dict.fromkeys(missing)))


def export_source_name_matcher_template(rows, rules):
    """asMappingUIExport's five settings, blank line and ordered joint rows."""
    return '\n'.join((
        'sideRight='+rules.right,'sideLeft='+rules.left,'sideMiddle='+rules.middle,
        'sideBeforeName='+str(int(rules.side_before_name)),
        'sideUnderScore='+str(int(rules.side_underscore)),'',
        *(row.fit_joint+'='+row.source_base for row in rows)))+'\n'


SOURCE_NAME_MATCHER_RESERVED = tuple(
    name+part for name in (
        'Root','Spine1','Spine2','Chest','Scapula','Shoulder','Elbow','Wrist','Cup',
        *(finger+'Finger'+str(index) for finger in ('Thumb','Index','Middle','Ring','Pinky')
          for index in range(1,5)),
        'Neck','Head','HeadEnd','Eye','EyeEnd','Jaw','JawEnd',
        'Hip','Knee','Ankle','Toes','ToesEnd') for part in ('','Part1','Part2'))
