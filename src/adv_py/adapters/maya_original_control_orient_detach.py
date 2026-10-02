"""asControlOrientDetach / Attach, ADV 6.925 MEL 6212–6455.

The source edits the actual controls. ParentMatrixHolder keeps the original
Extra.parentInverseMatrix space; Reverse holds their real driven children.
"""
import json
from adv_py.core.character_registry import safe_json, exact

from .maya_original_control_orient import (
    DETACH_HOLDER, MARKER, _has, _path, _parent, _children, _uuid, _by_uuid,
    _address, _add_all, _align_ik, _record, target, OrientTarget,
)
from .maya_original_control_identity import leaf, source_control_name, registration
from .maya_original_transform_channels import align_original_transform
from adv_py.core.original_control_orientation import original_control_identity

SESSION = 'advPySourceControlOrientSession'


def _session(c):
    plug = DETACH_HOLDER + '.' + SESSION
    if not c.objExists(plug):
        raise ValueError('Object asControlOrientDetachParentHolder not found; run Detach before Attach.')
    if not c.getAttr(plug, lock=True):
        raise ValueError('控制器方向分离记录已解锁')
    data = safe_json(c.getAttr(plug))
    if not isinstance(data, dict) or set(data) != {'version', 'rows'} or data['version'] != 1:
        raise ValueError('控制器方向分离记录无效')
    if not isinstance(data['rows'], list):
        raise ValueError('控制器方向分离成员记录无效')
    for row in data['rows']:
        exact(row, ('control', 'member', 'previous', 'holder', 'role', 'reverse'))
        if any(not isinstance(row[key], str) or not row[key]
               for key in ('control', 'member', 'previous', 'holder', 'role')):
            raise ValueError('控制器方向分离成员身份无效')
        if row['reverse'] is not None and not isinstance(row['reverse'], str):
            raise ValueError('控制器方向补偿层身份无效')
    return data['rows']


def detach_original_controls(host):
    host._require_transaction()
    c = host._cmds
    if c.objExists(DETACH_HOLDER):
        raise ValueError('All controllers have been Detached. Click Attach all controllers.')
    if not c.objExists('ControlSet'):
        raise ValueError('缺少 ControlSet')
    before = registration(host)
    selected = c.ls(selection=True, long=True) or []
    members = [_uuid(c, node) for node in c.sets('ControlSet', query=True) or []]
    host._transaction_changed = True
    holder = c.createNode('transform', name=DETACH_HOLDER)
    rows = []
    removed = []
    added = [holder]
    controls = []
    try:
        for member_id in members:
            member = _by_uuid(host, member_id)
            custom = any(_has(c, member, attribute) for attribute in
                         ('skinControl', 'clusterControl', 'softModControl'))
            role = source_control_name(host, member)
            if 'Extra' not in role and not custom:
                continue
            control = member if custom else _address(host, role.replace('Extra', '', 1))
            if not c.objExists(control):
                continue
            # Detach does not share Set Axis's Root/HipSwinger/RLA filters.
            # In MEL it traverses every Extra and supported custom control.
            info = original_control_identity(source_control_name(host, control))
            row = OrientTarget(control, info, '', None if custom else member, '', custom)
            control_id = _uuid(c, control)
            member_id = _uuid(c, member)
            orient = 'CustomOrient' + row.identity.role
            reverse = 'CustomOrientReverse' + row.identity.role
            has_orient = c.objExists(orient)
            matrix_holder = c.createNode('transform',
                name='CustomOrientParentMatrixHolder' + row.identity.role, parent=holder)
            matrix_holder_id = _uuid(c, matrix_holder)
            align_original_transform(c, matrix_holder, member)
            if custom and has_orient:
                align_original_transform(c, matrix_holder, _parent(c, orient))
            if has_orient:
                if not custom:
                    c.parent(control, orient)
                previous = _parent(c, orient)
                previous_id = _uuid(c, previous)
                member = _by_uuid(host, member_id)
                c.parent(member, previous, **({} if custom else {'relative': True}))
                member = c.parent(_by_uuid(host, member_id), _by_uuid(host, matrix_holder_id))[0]
                c.parent(reverse, holder)
                if not custom:
                    c.parent(_by_uuid(host, control_id), member)
                removed.append(_uuid(c, orient))
                c.delete(orient)
            else:
                previous = _parent(c, member)
                previous_id = _uuid(c, previous)
                c.parent(member, _by_uuid(host, matrix_holder_id))
                children = _children(c, _by_uuid(host, control_id))
                if children:
                    c.createNode('transform', name=reverse, parent=_by_uuid(host, control_id))
                    c.parent(reverse, holder)
                    c.parent(children, reverse)
            member = _by_uuid(host, member_id)
            attr = 'previousParent' + leaf(member)
            c.addAttr(holder, longName=attr, dataType='string')
            c.setAttr(holder + '.' + attr, previous, type='string')
            special_role = row.identity.kind + row.identity.name + 'X' + row.identity.side
            constraint = special_role + '_parentConstraint1'
            if c.objExists(constraint):
                if not c.objExists(reverse):
                    c.createNode('transform', name=reverse, parent=holder)
                c.addAttr(reverse, longName='hadXparentConstraint', attributeType='bool', defaultValue=True)
                c.delete(constraint)
            rows.append(dict(control=control_id, member=member_id, previous=previous_id,
                             holder=matrix_holder_id, role=row.identity.role,
                             reverse=_uuid(c, reverse) if c.objExists(reverse) else None))
            controls.append(_by_uuid(host, control_id))
            added.append(_by_uuid(host, matrix_holder_id))
            if c.objExists(reverse):
                added.append(_path(c, reverse))
        c.addAttr(holder, longName=SESSION, dataType='string')
        c.setAttr(holder + '.' + SESSION, json.dumps(dict(version=1, rows=rows),
                  separators=(',', ':')), type='string', lock=True)
        if before is not None:
            from .maya_control_orient_registration import refresh
            refresh(host, before, added=tuple(added), removed=tuple(removed))
    finally:
        surviving = [node for node in selected if c.objExists(node)]
        c.select(surviving, replace=True) if surviving else c.select(clear=True)
    return tuple(controls)


def attach_original_controls(host, *, mirror=True):
    host._require_transaction()
    c = host._cmds
    rows = _session(c)
    selected = c.ls(selection=True, long=True) or []
    before = registration(host)
    modified = []
    removed = []
    if before is not None:
        holder_path = _path(c, DETACH_HOLDER)
        removed.extend(node.uuid for node in before.nodes if node.path == holder_path
                       or node.path.startswith(holder_path + '|'))
    host._transaction_changed = True
    try:
        if mirror:
            from .maya_original_control_mirror import mirror_original_controls
            mirror_original_controls(host, side='R2L', space='Main', axis='X')
        for item in rows:
            member = _by_uuid(host, item['member'])
            control = _by_uuid(host, item['control'])
            previous = _by_uuid(host, item['previous'])
            altered = any(c.getAttr(control + '.' + attribute, settable=True)
                and abs(c.getAttr(control + '.' + attribute) - expected) > .01
                for attribute, expected in zip(('tx','ty','tz','rx','ry','rz','sx','sy','sz'),
                                               (0.,0.,0.,0.,0.,0.,1.,1.,1.)))
            if altered:
                orient = 'CustomOrient' + item['role']
                if c.objExists(orient):
                    removed.append(_uuid(c, orient))
                    c.delete(orient)
                c.createNode('transform', name=orient, parent=control)
                _add_all(c, orient, control)
                c.parent(orient, previous)
                c.parent(_by_uuid(host, item['member']), orient)
                control = _by_uuid(host, item['control'])
                if not _has(c, control, 'customAxis'):
                    c.addAttr(control, longName='customAxis', attributeType='bool')
                c.setAttr(control + '.customAxis', True)
                row = target(host, control)
                if row is not None:
                    _align_ik(c, row, control)
                modified.append(item)
            else:
                c.parent(member, previous)
        # Resolve saved pose paths by object identity after temporary parents
        # moved again. The source explicitly returns to Body build pose here.
        from .maya_control_orient_registration import refresh
        interim = before
        if before is not None:
            # MatrixHolder remains until children have been recovered. Refresh
            # all paths first so buildPose commands still address real objects.
            interim, _ = refresh(host, before, removed=tuple(removed),
                                 added=tuple('CustomOrient' + item['role'] for item in modified))
        host.apply_body_build_pose(host.read_body_build_pose())
        changed_roles = {item['role'] for item in modified}
        for item in rows:
            if not item['reverse']:
                continue
            reverse = _by_uuid(host, item['reverse'])
            control = _by_uuid(host, item['control'])
            if item['role'] in changed_roles:
                c.parent(reverse, control)
                reverse = _by_uuid(host, item['reverse'])
                _add_all(c, reverse, control)
                _record(c, 'CustomOrient' + item['role'], control, reverse)
            else:
                children = c.listRelatives(reverse, children=True, fullPath=True) or []
                if children:
                    c.parent(children, control)
            reverse = _by_uuid(host, item['reverse'])
            if _has(c, reverse, 'hadXparentConstraint'):
                from adv_py.core.original_control_orientation import original_control_identity
                info = original_control_identity(item['role'])
                special = info.kind + info.name + 'X' + info.side
                c.parentConstraint(control, _address(host, special), maintainOffset=True)
        c.delete(DETACH_HOLDER)
        if interim is not None:
            refresh(host, interim, removed=tuple(removed))
    finally:
        surviving = [node for node in selected if c.objExists(node)]
        c.select(surviving, replace=True) if surviving else c.select(clear=True)
    return len(modified)
