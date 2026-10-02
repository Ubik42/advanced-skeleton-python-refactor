"""Custom Orient Joints operations, ADV 6.925 MEL 62359–62519.

The export skeleton is a native duplicate. Skin transfer replaces the same
matrix edges and freezes their bind matrices; it does not resample weights.
"""
from adv_py.core.original_joint_orientation import original_game_joint_rotations
from .maya_original_control_orient import _uuid, _by_uuid, _parent
from .maya_original_control_identity import leaf

ROOT = 'GameSkeletonRoot_M'


def _joints(c, root):
    return tuple(c.listRelatives(root, allDescendents=True, type='joint', fullPath=True) or []) + (root,)


def create(host, primary='X', secondary='Y'):
    host._require_transaction()
    rotations = original_game_joint_rotations(primary, secondary)
    c = host._cmds
    if not c.objExists('Root_M'):
        raise ValueError('缺少 Root_M')
    host._transaction_changed = True
    if c.objExists(ROOT):
        c.delete(ROOT)
    root = c.duplicate('Root_M', name=ROOT)[0]
    root = c.parent(root, world=True)[0]
    descendants = c.listRelatives(root, allDescendents=True, type='joint', fullPath=True) or []
    identities = tuple((_uuid(c, joint), 'GameSkeleton' + leaf(joint)) for joint in descendants)
    for identity, name in identities:
        c.rename(_by_uuid(host, identity), name)
    identities = tuple(_uuid(c, joint) for joint in _joints(c, ROOT))
    for identity in identities:
        joint = _by_uuid(host, identity)
        children = tuple(_uuid(c, child) for child in
            c.listRelatives(joint, children=True, type='joint', fullPath=True) or [])
        parent = c.listRelatives(joint, parent=True, type='joint', fullPath=True) or []
        parent_id = _uuid(c, parent[0]) if parent else None
        if children:
            c.parent([_by_uuid(host, child) for child in children], world=True)
        if parent_id:
            c.parent(_by_uuid(host, identity), world=True)
        for rotation in rotations:
            c.rotate(*rotation, _by_uuid(host, identity), relative=True, objectSpace=True, forceOrder=True)
        if parent_id:
            c.parent(_by_uuid(host, identity), _by_uuid(host, parent_id))
        if children:
            c.parent([_by_uuid(host, child) for child in children], _by_uuid(host, identity))
    if c.objExists('DeformationSystem|root'):
        c.select(clear=True)
        c.joint(name='GameSkeletonRoot')
        c.parent(ROOT, 'GameSkeletonRoot')
    c.select(ROOT, replace=True)
    return tuple(_by_uuid(host, identity) for identity in identities)


def delete(host):
    host._require_transaction()
    c = host._cmds
    targets = [name for name in (ROOT, 'GameSkeletonRoot') if c.objExists(name)]
    if targets:
        host._transaction_changed = True
        c.delete(targets)
    return len(targets)


def disconnect(host):
    host._require_transaction()
    c = host._cmds
    removed = []
    for joint in _joints(c, ROOT):
        for suffix in ('_parentConstraint1', '_scaleConstraint1'):
            constraint = leaf(joint) + suffix
            if c.objExists(constraint):
                host._transaction_changed = True
                c.delete(constraint)
                removed.append(constraint)
    return tuple(removed)


def connect(host):
    host._require_transaction()
    disconnect(host)
    c = host._cmds
    host._transaction_changed = True
    constraints = []
    for joint in _joints(c, ROOT):
        source = leaf(joint).replace('GameSkeleton', '', 1)
        constraints.extend(c.parentConstraint(source, joint, maintainOffset=True))
        constraints.extend(c.scaleConstraint(source, joint, maintainOffset=True))
    return tuple(constraints)


def show_axis(host):
    host._require_transaction()
    c = host._cmds
    selected = c.ls(selection=True, long=True) or []
    host._transaction_changed = True
    try:
        c.select(ROOT, hierarchy=True)
        # Maya's built-in command toggles local axes using the selected joint
        # hierarchy. It is not an invocation of AdvancedSkeleton business MEL.
        from maya import mel
        mel.eval('ToggleLocalRotationAxes;')
    finally:
        c.select(selected, replace=True) if selected else c.select(clear=True)


def transfer_skin(host):
    host._require_transaction()
    c = host._cmds
    source = _joints(c, 'Root_M')
    destination = _joints(c, ROOT)
    if len(source) != len(destination):
        raise ValueError('原骨架与 GameSkeleton 的原版遍历列表长度不一致')
    host._transaction_changed = True
    transfer_back = False
    if c.objExists(ROOT + '.skinTransferred'):
        transfer_back = bool(c.getAttr(ROOT + '.skinTransferred'))
        c.setAttr(ROOT + '.skinTransferred', not transfer_back)
    else:
        c.addAttr(ROOT, longName='skinTransferred', attributeType='bool', defaultValue=True)
    if transfer_back:
        source, destination = destination, source
    skins = []
    for old, new in zip(source, destination):
        clusters = c.listConnections(old + '.worldMatrix[0]', type='skinCluster', plugs=False) or []
        plugs = c.listConnections(old + '.worldMatrix[0]', type='skinCluster', plugs=True) or []
        for plug in plugs:
            c.connectAttr(new + '.worldMatrix[0]', plug, force=True)
        for cluster in clusters:
            if cluster not in skins:
                skins.append(cluster)
    from .maya_deform_skinning import freeze_native_skin_cluster
    for skin in skins:
        freeze_native_skin_cluster(host.scene_address(skin))
    getattr(c, 'raw', c).dgdirty(allPlugs=True)
    return transfer_back, tuple(skins)
