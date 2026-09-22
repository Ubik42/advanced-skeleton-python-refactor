"""Ephemeral target-topology joint take for cross-spine-count FK retargeting."""
from math import sqrt
from uuid import uuid4

from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.spine_pose_resampling import resample_spine_world_matrices


def _short(path):
    return path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]


def _positions(matrices):
    points = tuple(matrix[12:15] for matrix in matrices)
    lengths = tuple(sqrt(sum((a-b)**2 for a, b in zip(left, right)))
                    for left, right in zip(points, points[1:]))
    total = sum(lengths)
    if total <= 1e-9 or any(length <= 1e-9 for length in lengths):
        raise CharacterRegistryError('跨段数迁移需要非退化脊柱链')
    running = 0.
    result = [0.]
    for length in lengths:
        running += length
        result.append(running / total)
    result[-1] = 1.
    return tuple(result)


def capture_resampled_character_source(host, source_namespace, target, frames):
    from .maya_body import MayaBodyBuildHost

    if not isinstance(source_namespace, str) or not source_namespace.strip():
        raise CharacterRegistryError('须明确指定来源角色命名空间')
    source_host = MayaBodyBuildHost(namespace=source_namespace)
    source = source_host.read_character_registration()
    if not isinstance(source.spine, BodySplinePlan):
        raise CharacterRegistryError('来源角色不是可变脊柱角色')
    if source_namespace == host.namespace:
        raise CharacterRegistryError('来源和目标不能是同一个角色')
    source_spine = tuple(_short(path) for path in source.spine.body_joints)
    target_spine = tuple(_short(path) for path in target.spine.body_joints)
    source_by_name = {_short(row.path): row.path for row in source.body}
    target_by_name = {_short(row.path): row.path for row in target.body}
    common_source = set(source_by_name) - set(source_spine[1:-1])
    common_target = set(target_by_name) - set(target_spine[1:-1])
    if common_source != common_target or source_spine[0] != target_spine[0] or source_spine[-1] != target_spine[-1]:
        raise CharacterRegistryError('跨段数迁移仅支持脊柱内部关节数变化，其余 Body 关节须同名')
    c = source_host._cmds
    old_time = float(c.currentTime(query=True))
    sampled = {}
    try:
        for frame in frames:
            c.currentTime(frame, edit=True)
            sampled[frame] = {name: tuple(float(x) for x in
                c.xform(path, query=True, worldSpace=True, matrix=True))
                for name, path in source_by_name.items()}
        c.currentTime(frames[0], edit=True)
        target_reference = tuple(tuple(float(x) for x in
            host._cmds.xform(path, query=True, worldSpace=True, matrix=True))
            for path in target.spine.body_joints)
    finally:
        c.currentTime(old_time, edit=True)
    # Bind correspondence is fixed at the first sample, even if spine lengths animate.
    source_positions = _positions(tuple(sampled[frames[0]][name] for name in source_spine))
    target_positions = _positions(target_reference)
    result = []
    for frame in frames:
        source_pose = sampled[frame]
        resampled = resample_spine_world_matrices(
            tuple(source_pose[name] for name in source_spine), target_positions,
            source_positions=source_positions)
        pose = {name: source_pose[name] for name in common_source}
        pose.update(zip(target_spine, resampled))
        result.append((frame, pose))
    return source, tuple(result)


def create_resampled_character_source(host, target, samples):
    host._require_transaction()
    from maya import cmds as c
    host._transaction_changed = True
    namespace = 'AdvPySpineBridge_' + uuid4().hex[:12]
    c.namespace(addNamespace=namespace)
    joints = {}
    for row in target.body:
        name = _short(row.path)
        parent = joints.get(_short(row.parent)) if row.parent else None
        if row.parent and parent is None:
            raise CharacterRegistryError('目标 Body 关节排序或父链不完整：' + name)
        joints[name] = c.createNode('joint', name=namespace + ':' + name,
                                    parent=parent, skipSelect=True)
    old_time = float(c.currentTime(query=True))
    try:
        for frame, pose in samples:
            c.currentTime(frame, edit=True)
            for row in target.body:
                name = _short(row.path)
                c.xform(joints[name], worldSpace=True, matrix=pose[name])
                for kind in ('translate', 'rotate'):
                    for axis in 'XYZ':
                        c.setKeyframe(joints[name], attribute=kind + axis, time=frame)
    finally:
        c.currentTime(old_time, edit=True)
    try:
        for frame, pose in samples:
            c.currentTime(frame, edit=True)
            for name, wanted in pose.items():
                actual = c.xform(joints[name], query=True, worldSpace=True, matrix=True)
                if max(abs(a-b) for a, b in zip(actual, wanted)) > 1e-4:
                    raise CharacterRegistryError('跨段数中间骨架采样矩阵不一致：'
                                                 + name + ' frame=' + str(frame))
    finally:
        c.currentTime(old_time, edit=True)
    return joints[_short(target.body_root)]


def delete_resampled_character_source(host, root):
    host._require_transaction()
    namespace = root.rsplit('|', 1)[-1].rsplit(':', 1)[0]
    from maya import cmds
    cmds.delete(root)
    cmds.namespace(removeNamespace=namespace)
