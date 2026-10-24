"""Custom Orient Joints operations, ADV 6.925 MEL 62359–62519.

The export skeleton is a native duplicate. Skin transfer replaces the same
matrix edges and freezes their bind matrices; it does not resample weights.
"""
from adv_py.core.original_joint_orientation import original_game_joint_rotations
from .maya_original_control_orient import _uuid, _by_uuid
from .maya_original_control_identity import leaf

ROOT = 'GameSkeletonRoot_M'


def retained_roots(host, registration):
    """The source's separate export skeleton survives a Body replacement.

    It stays outside the generated Body/AllSet and keeps its native objects.
    Existing parent/scale constraints are handed across as extension edges.
    """
    c = host._cmds
    if not c.objExists(ROOT):
        return ()
    roots = c.ls(ROOT, long=True, type='joint') or []
    if len(roots) != 1:
        raise ValueError('GameSkeletonRoot_M 缺失或不唯一')
    root = roots[0]
    if leaf(registration.body_root) != 'Root_M':
        return ()
    if root in {node.path for node in registration.nodes}:
        raise ValueError('GameSkeleton 不应替代已登记 Body')
    parents = c.listRelatives(root, parent=True, fullPath=True) or []
    if len(parents) == 1 and leaf(parents[0]) == 'GameSkeletonRoot':
        if c.nodeType(parents[0]) != 'joint':
            raise ValueError('GameSkeletonRoot 原版包装关节类型变化')
        root = parents[0]
    return (root,)


def _remove_python_build_metadata(c, joint):
    # Native duplicate copies our bookkeeping along with source joint data.
    # Export joints must not claim the original Body's identities or records.
    # Keep every native ADV field and every unknown authored attribute.
    from adv_py.core.character_generated_attributes import GENERATED_CHARACTER_ATTRIBUTES
    native = {'GameEngineScalingSSC', 'GameEngineScalingSX',
              'GameEngineScalingSY', 'GameEngineScalingSZ', 'originalParent'}
    for attribute in c.listAttr(joint, userDefined=True) or []:
        if attribute not in GENERATED_CHARACTER_ATTRIBUTES - native:
            continue
        plug = joint + '.' + attribute
        c.setAttr(plug, lock=False)
        c.deleteAttr(joint, attribute=attribute)


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
        _remove_python_build_metadata(c, joint)
        children = tuple(_uuid(c, child) for child in
            c.listRelatives(joint, children=True, type='joint', fullPath=True) or [])
        parent = c.listRelatives(joint, parent=True, type='joint', fullPath=True) or []
        parent_id = _uuid(c, parent[0]) if parent else None
        if children:
            c.parent([_by_uuid(host, child) for child in children], world=True)
        if parent_id:
            c.parent(_by_uuid(host, identity), world=True)
        for rotation in rotations:
            c.rotate(*rotation, _by_uuid(host, identity), relative=True, objectSpace=True, forceOrderXYZ=True)
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
    transfer_back = (bool(c.getAttr(ROOT + '.skinTransferred'))
        if c.objExists(ROOT + '.skinTransferred') else False)
    if transfer_back:
        source, destination = destination, source
    raw = getattr(c, 'raw', c)
    # These are production Skin nodes discovered only from the exact native
    # worldMatrix edges, and may live outside the rig namespace. Keep the
    # ordinary character boundary closed; make this explicit handoff here.
    transfers = []
    skins = []
    for old, new in zip(source, destination):
        old_plug = host.scene_address(old + '.worldMatrix[0]')
        new_plug = host.scene_address(new + '.worldMatrix[0]')
        plugs = raw.listConnections(old_plug, source=False, destination=True,
                                    type='skinCluster', plugs=True) or []
        for plug in plugs:
            if not raw.isConnected(old_plug, plug):
                raise ValueError('GameSkeleton 蒙皮矩阵连接在交接前变化：' + plug)
            transfers.append((old_plug, new_plug, plug))
            cluster = plug.split('.', 1)[0]
            if cluster not in skins:
                skins.append(cluster)
    host._transaction_changed = True
    if c.objExists(ROOT + '.skinTransferred'):
        c.setAttr(ROOT + '.skinTransferred', not transfer_back)
    else:
        c.addAttr(ROOT, longName='skinTransferred', attributeType='bool', defaultValue=True)
    # Reverse is decided by the same source skinTransferred flag. Discovery
    # must therefore use the actual old side, before changing that flag.
    for old, new, plug in transfers:
        raw.connectAttr(new, plug, force=True)
    from .maya_deform_skinning import freeze_native_skin_cluster
    for skin in skins:
        freeze_native_skin_cluster(skin, cmds=raw)
    raw.dgdirty(allPlugs=True)
    return transfer_back, tuple(skins)
