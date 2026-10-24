"""Native asMirror Body/Face transform sampling, ADV 6.925 MEL 12345.

The UI options enter as explicit values. All reads precede all pose writes,
just as the source accumulates its command string before evaluating it.
"""
from adv_py.core.original_control_mirror import original_mirror_order, original_mirror_sign
from .maya_original_control_identity import source_control_name, source_control_from_role, source_main
from .maya_original_control_orient import _path, _uuid, _by_uuid, DETACH_HOLDER


def mirror_original_controls(host, controls=None, *, side='R2L', space='Main', axis='X', ui_name='', ui_state=None):
    host._require_transaction()
    if side not in ('R2L', 'L2R', 'Flip') or space not in ('Main', 'Center', 'World') or axis not in ('X','Y','Z'):
        raise ValueError('原版镜像选项无效')
    c = host._cmds
    selected = c.ls(selection=True, long=True) or []
    if controls is None:
        from .maya_original_control_sets import resolve
        sets = resolve(host,ui_name,**(ui_state or {}))
        if not sets:
            raise ValueError('No controlSets detected. select a controller')
        controls = c.sets(sets, query=True) or []
    by_role = {}
    for control in controls:
        role = source_control_name(host, control)
        path = _path(c, control)
        if role in by_role and by_role[role] != path:
            raise ValueError('原版镜像控制器角色不唯一：' + role)
        by_role[role] = path
    stiff = frozenset(role for role, control in by_role.items() if c.objExists(control + '.stiff'))
    ordered = original_mirror_order(tuple(by_role), stiff=stiff)
    axes_z_minus_y = (c.objExists('FitSkeleton.primaryAxis') and c.objExists('FitSkeleton.secondaryAxis')
        and c.getAttr('FitSkeleton.primaryAxis') == 2 and c.getAttr('FitSkeleton.secondaryAxis') == 4)
    host._transaction_changed = True
    group = c.createNode('transform', name='flipGroup')
    group_id = _uuid(c, group)
    writes = []
    try:
        reference = None
        try:
            main = source_main(host)
        except ValueError:
            main = None
        if space == 'Main':
            reference = main
        elif space == 'Center':
            reference = source_control_from_role(host, 'RootX_M')
        if space == 'Center' or reference and c.objExists(reference):
            group = c.parent(group, reference)[0]
        c.xform(group, objectSpace=True, translation=(0., 0., 0.), rotation=(0., 0., 0.))
        if space in ('Main', 'Center') and main is not None:
            group = c.parent(group, world=True)[0]
        for role in ordered:
            source = by_role.get(role)
            if source is None:
                source = source_control_from_role(host, role)
                if not c.objExists(source):
                    continue
                source = _path(c, source)
            if 'Extra' in role and c.objExists(DETACH_HOLDER):
                continue
            if side != 'Flip' and (role.endswith('_M') or role.endswith('Main')):
                continue
            if side == 'R2L':
                if role.endswith('_L'):
                    continue
                destination_role = role.replace('_R', '_L', 1)
            elif side == 'L2R':
                if role.endswith('_R'):
                    continue
                destination_role = role.replace('_L', '_R', 1)
            else:
                if not role.endswith(('_R', '_L', '_M')) or role.endswith('FKExtraSpine1_M'):
                    continue
                destination_role = (role.replace('_L', '_R', 1) if role.endswith('_L') else
                                    role.replace('_R', '_L', 1) if role.endswith('_R') else role)
            destination = source_control_from_role(host, destination_role)
            if not c.objExists(destination):
                continue
            destination = _path(c, destination)
            custom = 'CustomSystem|' in source
            local = custom and c.objExists(source + '.localOrient') and bool(c.getAttr(source + '.localOrient'))
            ik_local = c.objExists(source + '.ikLocal')
            face = bool(c.objExists('FaceControlSet') and c.sets(source, isMember='FaceControlSet'))
            world = False
            positive = c.xform(destination, query=True, worldSpace=True, scale=True)[2] > 0
            for attribute in c.listAttr(source, keyable=True, multi=True, shortNames=True) or []:
                if attribute == 'v' or not c.attributeQuery(attribute, node=destination, exists=True):
                    continue
                dest_attr = (attribute.replace('_R', '_L', 1) if '_R' in attribute else
                             attribute.replace('_L', '_R', 1) if '_L' in attribute else attribute)
                factor = original_mirror_sign(role, dest_attr, positive_scale=positive,
                    local_custom=local, ik_local=ik_local, face=face, axes_z_minus_y=axes_z_minus_y)
                if (positive and (role.startswith(('IK', 'Pole', 'Roll', 'Pivot', 'RootX_M'))
                                  or custom and not local)
                        and not role.startswith(('IKLocal', 'IKhybrid')) and not ik_local):
                    world = True
                if role.startswith('Aim'):
                    continue
                if world and dest_attr in ('tx', 'ty', 'tz', 'rx', 'ry', 'rz'):
                    continue
                plug = destination + '.' + dest_attr
                if c.getAttr(plug, settable=True):
                    value = c.getAttr(source + '.' + attribute)
                    writes.append(('value', plug, value * factor))
            if world:
                loc1 = c.spaceLocator()[0]
                loc2 = c.spaceLocator()[0]
                id2 = _uuid(c, loc2)
                c.parent(loc2, loc1)
                loc1 = c.parent(loc1, source)[0]
                loc2 = _by_uuid(host, id2)
                c.xform(loc1, objectSpace=True, translation=(0., 0., 0.), rotation=(0., 0., 0.))
                order = c.getAttr(source + '.rotateOrder')
                c.setAttr(loc1 + '.rotateOrder', order)
                c.setAttr(loc2 + '.rotateOrder', order)
                c.setAttr(group + '.scale' + axis, 1.)
                loc1 = c.parent(loc1, group)[0]
                c.setAttr(group + '.scale' + axis, -1.)
                c.setAttr(loc1 + '.scaleX', -1.)
                loc2 = _by_uuid(host, id2)
                position = c.xform(loc2, query=True, worldSpace=True, translation=True)
                rotation = c.xform(loc2, query=True, worldSpace=True, rotation=True)
                writes.append(('world', destination, (position, rotation)))
            if c.objExists(source + '.mirror'):
                c.setAttr(source + '.mirror', False)
        c.delete(_by_uuid(host, group_id))
        for kind, destination, value in writes:
            if kind == 'value':
                c.setAttr(destination, value)
            else:
                c.xform(destination, worldSpace=True, translation=value[0], rotation=value[1])
    finally:
        raw = getattr(c, 'raw', c)
        if raw.ls(group_id):
            c.delete(_by_uuid(host, group_id))
        surviving = [node for node in selected if c.objExists(node)]
        c.select(surviving, replace=True) if surviving else c.select(clear=True)
    return len(writes)
