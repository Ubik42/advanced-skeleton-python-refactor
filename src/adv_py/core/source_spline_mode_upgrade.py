"""Resolve an explicit legacy Spline mode upgrade from the original Fit chain."""
from dataclasses import replace

from .character_registry import CharacterRegistryError
from .fit_ik import fit_joint_ik_info
from .source_fit_identity import source_fit_build_name
from .source_spline_mode import SourceSplineModePlan, source_mode_icon_scale


def plan_source_spline_mode_upgrade(spline, hierarchy, labels, *, fit_start=None):
    if not spline.source_curve_points:
        raise CharacterRegistryError('只有原版来源 Spline 可以升级独立 FKIK 控制器')
    if spline.source_mode is not None:
        return spline
    nodes = {joint.path: joint for joint in hierarchy.joints}
    identities = tuple(path.rsplit('|', 1)[-1] for path in spline.body_joints)
    side = identities[0].rsplit('_', 1)[-1]
    if side not in ('M', 'R', 'L') or any(not name.endswith('_' + side) for name in identities):
        raise CharacterRegistryError('旧 Spline 的 Body 侧标记不一致')
    matches = []
    for joint in hierarchy.joints:
        info = fit_joint_ik_info(hierarchy, labels, joint.path)
        if info is None or info.start != joint.path or info.solver != 'ikSplineSolver':
            continue
        names = tuple(source_fit_build_name(nodes[path].short_name) + '_' + side
                      for path in info.joints)
        if names == identities and (fit_start is None or info.start == fit_start):
            matches.append(info)
    if len(matches) != 1:
        raise CharacterRegistryError('旧 Spline 不能唯一对应原版 Fit IK 链')
    info = matches[0]
    parent = spline.body_joints[0].rsplit('|', 1)[0]
    if parent.rsplit('|', 1)[-1] == 'Root_M':
        parent = '|Group|MotionSystem|RootSystem|AdvPy_LegLockConstrained'
    elif not parent or parent.rsplit('|', 1)[-1] == 'DeformationSystem':
        parent = spline.body_joints[0]
    non_symmetry = any(part.rsplit(':', 1)[-1].endswith('_NonSymmetry')
                       for part in info.start.split('|'))
    name = lambda path: source_fit_build_name(nodes[path].short_name)
    mode = SourceSplineModePlan('FKIK' + info.name + '_' + side,
        nodes[info.start].short_name.rsplit(':', 1)[-1], parent,
        source_mode_icon_scale(hierarchy), sum(spline.lengths),
        name(info.start), name(info.middle), name(info.end),
        -1 if side == 'L' or non_symmetry else 1)
    return replace(spline, source_mode=mode,
                   source_fit_control_count=(spline.source_fit_control_count
                                             if spline.source_fit_control_count is not None
                                             else info.control_count))


def upgrade_mode_channels(channels, before, after):
    """Use fresh-build semantic keys and the new editable mode address."""
    mapping = {before.mode_plug: (after.mode_control, after.mode_attribute, 0., 10.)}
    mapping.update({before.visibility_settings + '.' + attribute:
                    (after.visibility_settings, attribute, row.minimum, row.maximum)
                    for attribute in ('autoVis', 'FKVis', 'IKVis')
                    for row in channels
                    if row.node + '.' + row.attribute == before.visibility_settings + '.' + attribute})
    return tuple(replace(row, key=(row.key.rsplit('.', 1)[0] + '.' + after.mode_attribute
                                  if plug == before.mode_plug else row.key),
                         node=mapping[plug][0], attribute=mapping[plug][1],
                         minimum=mapping[plug][2], maximum=mapping[plug][3])
                 if (plug := row.node + '.' + row.attribute) in mapping else row
                 for row in channels)
