"""Resolve native Face/Body roles against the retained Python Body graph."""
from .maya_original_control_identity import registration, source_control_from_role


def face_body_main(host):
    """Keep native Main when present; otherwise use its registered Python role."""
    return source_control_from_role(host, 'Main')


def face_body_fk_offset(host, joint):
    """Resolve the source FKOffset deletion root, including its optional layers."""
    c = host._cmds
    native = 'FKOffset' + joint
    if c.objExists(native):
        return native
    saved = registration(host)
    if saved is None:
        return native
    control = source_control_from_role(host, 'FK' + joint)
    matches = c.ls(control, long=True, type='transform') or []
    if not matches:
        return native
    owned = {row.path for row in saved.nodes}
    path = matches[0]
    while '|' in path:
        path = path.rsplit('|', 1)[0]
        if path in owned and path.rsplit('|', 1)[-1] == 'AdvPy_' + joint + 'FKOffset':
            return path
    raise ValueError('Body FK 控制缺少登记的原版 Offset 层：' + joint)


def face_body_aim_root(host, stem):
    c = host._cmds
    native = 'Aim' + stem
    if c.objExists(native):
        return native
    saved = registration(host)
    if saved is None:
        return native
    owned = {row.path for row in saved.nodes}
    for channel in saved.channels:
        if not channel.key.startswith(('generic.aim.' + stem + '.', 'fit.aim.' + stem + '.')):
            continue
        path = channel.node
        while '|' in path:
            if path in owned and path.rsplit('|', 1)[-1] == 'AdvPy_Aim' + stem:
                return path
            path = path.rsplit('|', 1)[0]
    return native


def face_body_joint_paths(host, body_paths):
    """Identify the source Face branch parented below a registered Body head.

    The native ordinary Face parents FaceJoint_M below Head (MEL 31549–31562).
    Its joints belong to FaceAllSet, not the Body joint-count/pose schema.
    Unknown joints elsewhere in the Body hierarchy remain visible to audits.
    """
    c = host._cmds
    roots = c.ls('FaceJoint_M', long=True, type='joint') or []
    if len(roots) != 1 or roots[0] not in body_paths:
        return frozenset()
    if not c.objExists('FaceAllSet') or not c.objExists('FaceFitSkeleton.HeadJoint'):
        return frozenset()
    parents = c.listRelatives(roots[0], parent=True, fullPath=True) or []
    heads = c.ls(c.getAttr('FaceFitSkeleton.HeadJoint'), long=True, type='joint') or []
    if parents != heads or len(heads) != 1:
        return frozenset()
    paths = {path for path in body_paths if path == roots[0] or path.startswith(roots[0] + '|')}
    if not all(c.sets(path, isMember='FaceAllSet') for path in paths):
        raise ValueError('Face 关节层级中存在没有归入 FaceAllSet 的关节')
    return frozenset(paths)
