"""Native asAlignFKIK reverse QToes aim, MEL 10945–10973."""
from adv_py.core.character_registry import CharacterRegistryError
from .maya_source_limb_pole import _temporary_id, _delete_temporary


def align_original_reverse_roll(host, binding):
    host._require_transaction()
    c = host._cmds
    roll = binding.reverse_roll
    if not roll:
        return
    # The local-orient handle can be below the direct handle's parent. ADV
    # deliberately discovers descendants, rather than the build's handle.
    handles = c.listRelatives(roll, allDescendents=True, type='ikHandle', fullPath=True) or []
    parents = c.listRelatives(roll, parent=True, fullPath=True) or []
    if not handles or len(parents) != 1:
        raise CharacterRegistryError('QToes 反向对齐缺少原版 IK handle 或父层：' + roll)
    target = binding.joints[binding.primary_count - 1].control
    direction = -1. if binding.side == 'L' else 1.
    first_id = second_id = None
    try:
        first = c.createNode('transform', name='tempXform1', parent=handles[0])
        first_id = _temporary_id(c, first)
        second = c.createNode('transform', name='tempXform2', parent=roll)
        second_id = _temporary_id(c, second)
        c.parent(second, first, absolute=True)
        first = c.parent(first, parents[0], absolute=True)[0]
        raw = getattr(c, 'raw', c)
        # Parenting changes full DAG paths. Use UUID only for locating this
        # operation's own temporary; subsequent calls stay character scoped.
        second = raw.ls(second_id, long=True)[0]
        if hasattr(c, 'identity'):
            second = c.identity.to_local(second)
        c.aimConstraint(target, first, offset=(0., 0., 0.), weight=1.,
                        aimVector=(-direction, 0., 0.), upVector=(0., direction, 0.),
                        worldUpType='objectrotation', worldUpObject=target)
        rotation = c.xform(second, query=True, worldSpace=True, rotation=True)
        c.xform(roll, worldSpace=True, rotation=tuple(rotation))
        host._transaction_changed = True
    finally:
        _delete_temporary(c, second_id)
        _delete_temporary(c, first_id)
