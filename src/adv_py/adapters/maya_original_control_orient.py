"""Native asSetControlOrient, ADV 6.925 MEL 5684–6188.

All authored control rotation stays on the original control. The source's
CustomOrient/CustomOrientReverse hierarchy supplies and cancels the new frame.
No rotateAxis edits or calibrated multiplyDivide sign network is substituted.
"""
from dataclasses import dataclass
from fnmatch import fnmatchcase
import json
import re

from adv_py.core.original_control_orientation import (
    AXES, OriginalControlOrientOptions, original_control_identity,
)
from .maya_original_control_identity import (
    leaf, registration as saved_registration, source_control_name,
    source_control_from_role,
)
from .maya_original_rla_child import original_non_part_rla_child, original_rla_child
from .maya_original_transform_channels import align_original_transform

SET_HOLDER = 'asSetControlOrientParentHolder'
DETACH_HOLDER = 'asControlOrientDetachParentHolder'
MARKER = 'advPySourceControlOrient'
FRAME_KEYS = ('control', 'reverse', 'control_uuid', 'reverse_uuid')


def _path(c, node):
    paths = c.ls(node, long=True) or []
    if len(paths) != 1:
        raise ValueError('控制器朝向对象缺失或不唯一：' + node)
    return paths[0]


def _uuid(c, node):
    return c.ls(node, uuid=True)[0]


def _by_uuid(host, identity):
    c = host._cmds
    raw = getattr(c, 'raw', c)
    paths = raw.ls(identity, long=True) or []
    if len(paths) != 1:
        raise ValueError('控制器朝向原对象身份失效：' + identity)
    boundary = getattr(c, 'identity', None)
    if boundary is not None:
        if not boundary.owns(paths[0]):
            raise ValueError('控制器朝向对象越过角色命名空间')
        return boundary.to_local(paths[0])
    return paths[0]


def _parent(c, node):
    return (c.listRelatives(node, parent=True, fullPath=True) or [None])[0]


def _children(c, node):
    return c.listRelatives(node, children=True, fullPath=True, type='transform') or []


def _has(c, node, attribute):
    return bool(c.objExists(node + '.' + attribute))


def _warn(c, text):
    c.warning(text)


def _address(host, role):
    return source_control_from_role(host, role)


@dataclass(frozen=True)
class OrientTarget:
    control: str
    identity: object
    deform: str
    extra: str | None
    offset: str
    custom: bool = False
    cluster: bool = False
    soft_mod: bool = False
    sub: str | None = None
    align: str | None = None


def target(host, requested):
    """Resolve original roles to this graph's actual FK / RP objects."""
    c = host._cmds
    control = _path(c, requested)
    info = original_control_identity(source_control_name(host, control))
    custom = any(_has(c, control, attribute) for attribute in
                 ('skinControl', 'clusterControl', 'softModControl', 'SquashControl'))
    if _has(c, control, 'SquashControl'):
        _warn(c, 'Unable to CustomOrient SquashController: "' + info.role + '", skipping this.')
        return None
    if not c.objExists('ControlSet') or not c.sets(control, isMember='ControlSet'):
        _warn(c, '"' + info.role + '" is not a member of ControlSet, skipping this.')
        return None
    if info.kind in ('Root', 'HipSwinger', 'Extra') or 'Extra' in info.kind:
        _warn(c, 'Unable to CustomOrient controller-type: ' + info.kind + ', skipping this.')
        return None
    if not info.kind and not custom:
        _warn(c, 'Unable to determine controller-type for: ' + info.role)
        return None
    deform = info.name + info.side
    align = None
    saved = saved_registration(host)
    for limb in saved.source_limbs if saved is not None else ():
        if leaf(control) in (leaf(limb.ik_control), leaf(limb.pole_control)):
            deform = limb.joints[limb.middle_index if info.kind == 'Pole'
                                 else limb.primary_count - 1].body
            if info.kind == 'IK':
                align = limb.align
            break
        if (info.kind == 'IKLocal' and info.name == limb.label
                and info.side == '_' + limb.side):
            deform = limb.joints[limb.primary_count - 1].body
            break
        if limb.toe_control and leaf(control) == leaf(limb.toe_control):
            deform = next((joint.body for joint in limb.joints
                           if leaf(joint.fk_driver) == leaf(limb.toe_source)), limb.toe_source)
            align = limb.toe_align
            break
        for hybrid in limb.hybrid_controls:
            if leaf(control) == leaf(hybrid.control):
                deform = next((joint.body for joint in limb.joints
                               if leaf(joint.fk_driver) == leaf(hybrid.fk_driver)), hybrid.fk_driver)
                break
    cluster = _has(c, control, 'clusterControl')
    soft_mod = _has(c, control, 'softModControl')
    if custom:
        if _has(c, control, 'parent'):
            deform = c.getAttr(control + '.parent')
        extra_role = ('Subtract' + info.name + info.side if cluster else
                      info.name + 'Base' + info.side if soft_mod else
                      info.kind + info.name + 'Subtract' + info.side)
        extra = _address(host, extra_role) if not _has(c, control, 'skinControl') else None
        offset = _address(host, info.name + 'Base' + info.side if soft_mod else
                          info.kind + 'Offset' + info.name + info.side)
    else:
        extra = _address(host, info.kind + 'Extra' + info.name + info.side)
        if not c.objExists(extra):
            parent = _parent(c, control)
            if parent and 'Extra' in leaf(parent):
                extra = parent
        offset = _address(host, info.kind + 'Offset' + info.name + info.side)
        if not c.objExists(offset) and extra and c.objExists(extra):
            parent = _parent(c, extra)
            # After a first edit Extra's parent is CustomOrient; its parent
            # is the source Offset. No new name convention is introduced.
            if parent and leaf(parent).startswith('CustomOrient'):
                parent = _parent(c, parent)
            if parent:
                offset = parent
    if info.kind in ('Bend', 'BendX') and re.search(r'[0-9]$', info.name):
        deform = info.name[:-1] + info.side
    if extra is not None and not c.objExists(extra):
        _warn(c, 'Unable to find Extra controller: ' + str(extra))
        return None
    if not c.objExists(offset) or not c.objExists(deform):
        _warn(c, 'Unable to find controller Offset or deformJoint: ' + info.role)
        return None
    children = _children(c, control)
    sub = children[0] if (children and 'Sub' in leaf(children[0])
                         and c.sets(children[0], isMember='ControlSet')) else None
    return OrientTarget(control, info, deform, extra, offset, custom, cluster,
                        soft_mod, sub, align)


def _store_options(c, control, options):
    for name, axis in (('primaryAxis', options.primary), ('secondaryAxis', options.secondary)):
        if not _has(c, control, name):
            c.addAttr(control, longName=name, attributeType='enum', enumName=':'.join(AXES) + ':')
        c.setAttr(control + '.' + name, AXES.index(axis))
    for name, value in (
        ('worldorient', options.world_orient), ('worldmatch', options.world_match),
        ('curveUnafeccted', options.curve_unaffected), ('mirror', options.mirror),
        ('mirroredBehaviour', options.mirrored_behaviour),
        ('mirroredTranslate', options.mirrored_translate),
    ):
        if not _has(c, control, name):
            c.addAttr(control, longName=name, attributeType='bool')
        c.setAttr(control + '.' + name, value)


def read_options(c, control):
    def flag(attribute):
        return bool(c.getAttr(control + '.' + attribute)) if _has(c, control, attribute) else False
    def axis(attribute, default):
        return c.getAttr(control + '.' + attribute, asString=True) if _has(c, control, attribute) else default
    return OriginalControlOrientOptions(axis('primaryAxis', 'X'), axis('secondaryAxis', 'Y'),
        flag('worldorient'), flag('worldmatch'), flag('curveUnafeccted'), flag('mirror'),
        flag('mirroredBehaviour'), flag('mirroredTranslate'))


def _curve_points(c, controls):
    rows = []
    for control in controls:
        for shape in c.listRelatives(control, shapes=True, type='nurbsCurve', fullPath=True) or []:
            count = c.getAttr(shape + '.spans') + c.getAttr(shape + '.degree')
            rows.append((_uuid(c, shape), tuple(tuple(c.xform(
                shape + '.cv[' + str(index) + ']', query=True, worldSpace=True, translation=True))
                for index in range(count))))
    return tuple(rows)


def _restore_points(host, rows):
    for identity, points in rows:
        shape = _by_uuid(host, identity)
        for index, position in enumerate(points):
            host._cmds.xform(shape + '.cv[' + str(index) + ']', worldSpace=True, translation=position)


def _add_all(c, node, control):
    if c.objExists('AllSet') and c.sets(control, isMember='AllSet'):
        c.sets(node, add='AllSet')


def _align_ik(c, row, control):
    align = row.align
    native = 'AlignIKTo' + row.identity.name + row.identity.side
    if c.objExists(native):
        align = native
    if row.identity.kind == 'IK' and align and c.objExists(align):
        c.delete(c.orientConstraint(control, align))
        if not _has(c, align, 'CustomOrient'):
            c.addAttr(align, longName='CustomOrient', attributeType='bool', defaultValue=True, keyable=False)


def _rla(c, row):
    child = original_non_part_rla_child(c, row.deform)
    if not child:
        for pattern in ('Partial', 'startSlider[0-9]', 'middleSlider[0-9]', 'endSlider[0-9]'):
            if fnmatchcase(row.deform, '*' + pattern + '*'):
                base = re.sub(pattern, '', row.deform, count=1)
                child = original_rla_child(c, base)
    return child


def _world_match(c, row, sampler):
    root = c.createNode('transform', name='tempWSsampler1')
    align_original_transform(c, root, row.deform, True, False)
    child = c.createNode('transform', name='tempWSsampler2', parent=root)
    child = c.parent(child, row.deform)[0]
    c.setAttr(child + '.tx', 1.)
    align_original_transform(c, sampler, child, True, False)
    child = c.parent(child, root)[0]
    position = c.getAttr(child + '.t')[0]
    aim = (1., 0., 0.)
    for axis in range(3):
        if all(abs(position[axis]) > abs(position[other]) for other in range(3) if other != axis):
            aim = tuple((1. if position[axis] >= 0 else -1.) if index == axis else 0.
                        for index in range(3))
    up = (0., 0., 1.) if aim[1] else (0., 1., 0.)
    c.delete(root)
    return aim, up, up


def _set_one(host, row, options, *, reverse=False, custom_frame=None):
    c = host._cmds
    control_id = _uuid(c, row.control)
    extra_id = _uuid(c, row.extra) if row.extra else None
    sub_id = _uuid(c, row.sub) if row.sub else None
    rla = _rla(c, row)
    if not rla and not (options.world_orient or options.world_match):
        _warn(c, 'Unable to RLA-Child for: ' + row.identity.role + ' to aim-at, skipping this.')
        return None, ()
    custom = 'CustomOrient' + row.identity.role
    reverse_name = 'CustomOrientReverse' + row.identity.role
    if custom_frame is None:
        _store_options(c, row.control, options)
    if _has(c, row.control, 'customAxis') and c.getAttr(row.control + '.customAxis') and custom_frame is None:
        old_parent = _parent(c, custom)
        c.parent(row.extra or row.control, old_parent, relative=True)
        children = _children(c, reverse_name)
        if children:
            c.parent(children, _by_uuid(host, sub_id or control_id), relative=True)
        c.delete(custom, reverse_name)
        c.setAttr(_by_uuid(host, control_id) + '.customAxis', False)
    control = _by_uuid(host, control_id)
    extra = _by_uuid(host, extra_id) if extra_id else None
    sub = _by_uuid(host, sub_id) if sub_id else None
    parent = _parent(c, extra or control)
    children = _children(c, sub or control)
    points = _curve_points(c, (control, sub) if sub else (control,)) if options.curve_unaffected else ()
    holder = c.createNode('transform', name=SET_HOLDER)
    changed_edges = []
    if not c.objExists(reverse_name):
        reverse_node = c.createNode('transform', name=reverse_name, parent=control)
        _add_all(c, reverse_node, control)
        if children:
            c.parent(children, reverse_node)
    c.parent(reverse_name, holder)
    if not c.objExists(custom):
        c.createNode('transform', name=custom, parent=parent)
        _add_all(c, custom, control)
        if extra:
            # Original Inbetween uses Extra.parentInverseMatrix. Preserve its
            # old space before putting Extra below the new orientation frame.
            outputs = c.listConnections(extra + '.parentInverseMatrix', source=False,
                                        destination=True, plugs=True) or []
            restore = ''
            for destination in outputs:
                source = extra + '.parentInverseMatrix'
                replacement = parent + '.worldInverseMatrix'
                c.connectAttr(replacement, destination, force=True)
                changed_edges.append((source, destination, replacement))
                dest_node, dest_attr = destination.split('.', 1)
                restore += ('connectAttr -f ' + leaf(extra) + '.parentInverseMatrix '
                            + leaf(dest_node) + '.' + dest_attr + ';')
            if restore:
                if not _has(c, extra, 'CustomOrientRestoreCmd'):
                    c.addAttr(extra, longName='CustomOrientRestoreCmd', dataType='string')
                c.setAttr(extra + '.CustomOrientRestoreCmd', restore, type='string')
            c.parent(extra, custom)
        else:
            c.parent(control, custom)
    special = row.identity.kind + row.identity.name + 'X' + row.identity.side
    constraint = special + '_parentConstraint1'
    had_constraint = c.objExists(constraint)
    if had_constraint:
        c.delete(constraint)
    c.setAttr(custom + '.s', *((-1.,)*3 if row.identity.side == '_L'
              and options.mirrored_translate else (1.,)*3), type='float3')
    position = None
    if row.custom and rla:
        position = c.xform(custom, query=True, worldSpace=True, translation=True)
        align_original_transform(c, custom, _parent(c, rla), True, False)
    sampler = c.createNode('transform', name='tempAimAtTarget')
    if rla:
        align_original_transform(c, sampler, rla)
    if 'Slider' in row.deform:
        sampler = c.parent(sampler, row.deform)[0]
        c.setAttr(sampler + '.t', 1., 0., 0., type='float3')
        sampler = c.parent(sampler, world=True)[0]
    control = _by_uuid(host, control_id)
    if options.world_orient or options.world_match:
        align_original_transform(c, sampler, control)
        c.move(1., 0., 0., sampler, worldSpace=True, relative=True)
    aim, up, object_up = options.aim_vectors(reverse=reverse)
    world_up = (0., 0., 1.)
    if options.world_match:
        aim, up, world_up = _world_match(c, row, sampler)
        if reverse and options.mirrored_behaviour:
            up = tuple(-value for value in up)
    up_node = None
    kwargs = dict(offset=(0., 0., 0.), weight=1., aimVector=aim, upVector=up)
    if options.world_orient or options.world_match:
        kwargs.update(worldUpType='vector', worldUpVector=world_up)
    else:
        up_node = c.createNode('transform', name='tempAimUpVec', parent=row.deform)
        up_node = c.parent(up_node, world=True)[0]
        kwargs.update(worldUpType='objectrotation', worldUpVector=object_up, worldUpObject=up_node)
    c.delete(c.aimConstraint(sampler, custom, **kwargs))
    if position is not None:
        c.xform(custom, worldSpace=True, translation=position)
    c.delete(sampler)
    if up_node:
        c.delete(up_node)
    if row.cluster:
        temp = c.createNode('transform', name='tempMatrixXform')
        align_original_transform(c, temp, row.identity.name + row.identity.side, False, True)
        matrix = c.xform(temp, query=True, objectSpace=True, matrix=True)
        c.setAttr('MMT' + row.identity.name + row.identity.side + '.matrixIn[1]', *matrix, type='matrix')
        c.setAttr('MMR' + row.identity.name + row.identity.side + '.matrixIn[2]', *matrix, type='matrix')
        c.setAttr('MMR' + row.identity.name + row.identity.side + '.matrixIn[0]',
                  *c.getAttr(temp + '.inverseMatrix'), type='matrix')
        c.delete(temp)
    if custom_frame is not None:
        c.xform(custom, objectSpace=True, matrix=custom_frame)
    control = _by_uuid(host, control_id)
    c.parent(reverse_name, control)
    if sub_id:
        c.parent(reverse_name, _by_uuid(host, sub_id), relative=True)
    _restore_points(host, points)
    c.delete(holder)
    _align_ik(c, row, control)
    if had_constraint:
        c.parentConstraint(control, _address(host, special), maintainOffset=True)
    _record(c, custom, control, _path(c, reverse_name))
    return control, tuple(changed_edges)


def _record(c, custom, control, reverse):
    if not _has(c, custom, MARKER):
        c.addAttr(custom, longName=MARKER, dataType='string')
    c.setAttr(custom + '.' + MARKER, lock=False)
    c.setAttr(custom + '.' + MARKER, json.dumps(dict(control=control, reverse=reverse,
              control_uuid=_uuid(c, control), reverse_uuid=_uuid(c, reverse)),
              separators=(',', ':')), type='string', lock=True)


def set_original_control_orient(host, controls, options, *, batch=False, custom_frames=None):
    host._require_transaction()
    c = host._cmds
    if c.objExists(DETACH_HOLDER):
        raise ValueError('Can not Set Axis when controllers are Detached.')
    if c.objExists(SET_HOLDER):
        raise ValueError('Found previous failed Set Axis parent holder; undo that operation first.')
    if not controls:
        raise ValueError('Nothing Selected, select controller first.')
    selected = c.ls(selection=True, long=True) or []
    before = saved_registration(host)
    original_count = len(controls)
    pending = [_uuid(c, control) for control in controls]
    modified = []
    edges = []
    removable = []
    if before is not None:
        for node in before.nodes:
            if _has(c, node.path, MARKER):
                removable.append(node.uuid)
                reverse = json.loads(c.getAttr(node.path + '.' + MARKER))['reverse']
                removable.append(_uuid(c, reverse))
    start_left = False
    host._transaction_changed = True
    try:
        index = 0
        while index < len(pending):
            requested = _by_uuid(host, pending[index])
            in_mirror_run = index >= original_count
            index += 1
            row = target(host, requested)
            if row is None:
                continue
            settings = read_options(c, row.control) if batch else options
            if not in_mirror_run:
                start_left = row.identity.side == '_L'
            if settings.mirror and not in_mirror_run and row.identity.side in ('_R', '_L'):
                opposite = _address(host, row.identity.role[:-1] + ('L' if row.identity.side == '_R' else 'R'))
                if c.objExists(opposite):
                    opposite_id = _uuid(c, opposite)
                    if opposite_id not in pending:
                        pending.append(opposite_id)
            frame = (custom_frames or {}).get(row.identity.role)
            result, replaced = _set_one(host, row, settings,
                reverse=start_left or in_mirror_run, custom_frame=frame)
            if result:
                modified.append(_uuid(c, result))
                edges.extend(replaced)
        if before is not None and modified:
            from .maya_control_orient_registration import refresh
            refresh(host, before, edges=tuple(edges), removed=tuple(removable))
    finally:
        surviving = [value for value in selected if c.objExists(value)]
        c.select(surviving, replace=True) if surviving else c.select(clear=True)
    return tuple(_by_uuid(host, identity) for identity in modified)
