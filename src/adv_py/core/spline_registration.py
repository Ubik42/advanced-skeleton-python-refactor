"""Closed spline payload decoder for version 2 character registrations."""
from dataclasses import fields

from .body_spline import BodySplinePlan
from .body_limb_mechanisms import BodyLimbMechanismJointSpec, BodyLimbMechanismRole
from .fit_symmetry import FitBuildSide


def decode_spline(raw, body):
    from .character_registry import exact, path, vector, CharacterRegistryError

    exact(raw, (field.name for field in fields(BodySplinePlan)))
    body_paths = tuple(path(p) for p in raw['body_joints'])
    count = len(body_paths)
    if not 2 <= count <= 64 or len(set(body_paths)) != count:
        raise CharacterRegistryError('曲线脊柱关节数量或身份无效')
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
    controls = tuple(path(control) for control in raw['fk_controls'])
    if len(positions) != 4 or len(targets) != 4 or len(set(targets)) != 4 or len(controls) != count or len(set(controls)) != count:
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
                          path(raw['chest_space']), targets, positions, axes, lengths)
