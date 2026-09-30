"""Closed spline payload decoder for version 2 character registrations."""
from dataclasses import fields

from .body_spline import BodySplinePlan
from .body_limb_mechanisms import BodyLimbMechanismJointSpec, BodyLimbMechanismRole
from .fit_symmetry import FitBuildSide


def decode_spline(raw, body):
    from .character_registry import exact, path, vector, CharacterRegistryError

    if isinstance(raw, dict) and 'use_offset_parent_matrix' not in raw:
        raw = {**raw, 'use_offset_parent_matrix': False}
    if isinstance(raw, dict) and 'even_stretch_graph' not in raw:
        raw = {**raw, 'even_stretch_graph': False}
    if isinstance(raw, dict) and 'twist_ramp_graph' not in raw:
        raw = {**raw, 'twist_ramp_graph': False}
    if isinstance(raw, dict) and 'mid_follow_graph' not in raw:
        raw = {**raw, 'mid_follow_graph': False}
    if isinstance(raw, dict) and 'isolated_mid_follow_graph' not in raw:
        raw = {**raw, 'isolated_mid_follow_graph': False}
    if isinstance(raw, dict) and 'sub_targets' not in raw:
        raw = {**raw, 'sub_targets': [], 'extra_curve': False}
    if isinstance(raw, dict) and 'fk_root_point_from_receiver' not in raw:
        raw = {**raw, 'fk_root_point_from_receiver': False}
    exact(raw, (field.name for field in fields(BodySplinePlan)))
    if type(raw['use_offset_parent_matrix']) is not bool:
        raise CharacterRegistryError('Spline OPM 开关无效')
    if type(raw['even_stretch_graph']) is not bool:
        raise CharacterRegistryError('Spline stretchEven 图标记无效')
    if (type(raw['twist_ramp_graph']) is not bool
            or (raw['twist_ramp_graph'] and not raw['even_stretch_graph'])):
        raise CharacterRegistryError('Spline 中间扭转图标记无效')
    if (type(raw['mid_follow_graph']) is not bool
            or (raw['mid_follow_graph'] and not raw['twist_ramp_graph'])):
        raise CharacterRegistryError('Spline 中间跟随图标记无效')
    if (type(raw['isolated_mid_follow_graph']) is not bool
            or (raw['isolated_mid_follow_graph'] and not raw['mid_follow_graph'])):
        raise CharacterRegistryError('Spline 独立跟随层标记无效')
    if type(raw['extra_curve']) is not bool:
        raise CharacterRegistryError('Spline IK Extra 曲线标记无效')
    if type(raw['fk_root_point_from_receiver']) is not bool:
        raise CharacterRegistryError('Spline FK 位置来源开关无效')
    body_paths = tuple(path(p) for p in raw['body_joints'])
    count = len(body_paths)
    if not 2 <= count <= 64 or len(set(body_paths)) != count:
        raise CharacterRegistryError('曲线脊柱关节数量或身份无效')
    if raw['twist_ramp_graph'] and count<=2:
        raise CharacterRegistryError('两关节 Spline 不使用中间扭转曲线')
    if raw['mid_follow_graph'] and count<=2:
        raise CharacterRegistryError('两关节 Spline 不使用中间跟随图')
    by_path = {joint.path: joint for joint in body}
    if any(p not in by_path for p in body_paths) or any(
        by_path[p].parent != parent for parent, p in zip(body_paths, body_paths[1:])
    ):
        raise CharacterRegistryError('曲线脊柱必须对应实际 Body 父链')
    root = path(raw['root_path'])
    lengths = vector(raw['lengths'], count - 1)
    if min(lengths) <= 0:
        raise CharacterRegistryError('曲线脊柱骨段长度必须为正')
    axes = tuple(vector(axis, 3) for axis in raw['axes'])
    if len(axes) != 3 or any(abs(sum(a*b for a,b in zip(left,right)) - (i == j)) > 1e-5
                             for i,left in enumerate(axes) for j,right in enumerate(axes)):
        raise CharacterRegistryError('曲线脊柱朝向必须正交归一')
    positions = tuple(vector(position, 3) for position in raw['positions'])
    targets = tuple(path(target) for target in raw['targets'])
    subs = tuple(path(target) for target in raw['sub_targets'])
    if subs and (len(subs) != len(targets) or any(
            sub != target+f'|AdvPy_SplineIK{index}Sub'
            for index, (target, sub) in enumerate(zip(targets, subs)))):
        raise CharacterRegistryError('Spline IK Sub 控制器层级无效')
    has_extras = all(target.rsplit('|', 1)[0].rsplit('|', 1)[-1]
                     == f'AdvPy_SplineIK{index}Extra'
                     for index, target in enumerate(targets))
    if raw['extra_curve'] and not has_extras:
        raise CharacterRegistryError('Spline IK Extra 曲线缺少父层')
    for index, target in enumerate(targets):
        offset = (target.rsplit('|', 2)[0] if has_extras
                  else target.rsplit('|', 1)[0])
        if offset.rsplit('|', 1)[-1] != f'AdvPy_SplineIK{index}Offset':
            raise CharacterRegistryError('Spline IK Offset 层级无效')
    if raw['isolated_mid_follow_graph']:
        for index, target in enumerate(targets):
            parent = (raw['pelvis_control']+'|AdvPy_SplineIKFollowMain'
                      if 0<index<len(targets)-1 else raw['pelvis_control'])
            offset = parent+f'|AdvPy_SplineIK{index}Offset'
            expected = (offset+f'|AdvPy_SplineIK{index}Extra|AdvPy_SplineIK{index}'
                        if has_extras else offset+f'|AdvPy_SplineIK{index}')
            if target != expected:
                raise CharacterRegistryError('曲线脊柱 IK 控制器层级与跟随模式不一致')
    controls = tuple(path(control) for control in raw['fk_controls'])
    if (len(targets) not in (4,max(4,count+1)) or len(positions)!=len(targets)
            or len(set(targets)) != len(targets) or len(controls) != count or len(set(controls)) != count):
        raise CharacterRegistryError('曲线脊柱控制器声明不完整')
    joints = []
    for index, row in enumerate(raw['joints']):
        exact(row, (field.name for field in fields(BodyLimbMechanismJointSpec)))
        node = path(row['path'])
        joint_axes = tuple(vector(axis, 3) for axis in row['world_axes'])
        if len(joint_axes) != 3 or row['name'] != node.rsplit('|', 1)[-1]:
            raise CharacterRegistryError('曲线脊柱机制关节描述无效')
        joint = BodyLimbMechanismJointSpec(
            BodyLimbMechanismRole(row['role']), FitBuildSide(row['side']), path(row['source_joint']),
            node, row['name'], path(row['parent_path']), vector(row['world_position'], 3), joint_axes)
        expected_parent = root if index % count == 0 else joints[-1].path
        if (index >= count * 2 or joint.source_joint != body_paths[index % count]
                or joint.role.value != ('fk' if index < count else 'ik')
                or joint.parent_path != expected_parent or node.rsplit('|', 1)[0] != expected_parent):
            raise CharacterRegistryError('曲线脊柱机制链顺序或父级无效')
        joints.append(joint)
    if len(joints) != count * 2:
        raise CharacterRegistryError('曲线脊柱机制链不完整')
    return BodySplinePlan(root, tuple(joints), body_paths, controls, path(raw['pelvis_control']),
                          path(raw['chest_space']), targets, positions, axes,
                          lengths, raw['use_offset_parent_matrix'],
                          raw['even_stretch_graph'], raw['twist_ramp_graph'],
                          raw['mid_follow_graph'], raw['isolated_mid_follow_graph'],
                          subs, raw['extra_curve'],
                          raw['fk_root_point_from_receiver'])
