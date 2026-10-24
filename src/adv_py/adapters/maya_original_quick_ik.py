"""asQuickIK, ADV 6.925 MEL 13701–13874.

Create the original temporary joint chain and its native RP controls. No
replacement solver, curve sampler, or rest-pose synthesis is used here.
"""
from dataclasses import dataclass
from math import dist

from adv_py.core.source_control_identity import source_fk_bindings, source_leaf
from .maya_original_control_identity import registration


@dataclass(frozen=True)
class OriginalQuickIK:
    start_joint: str
    end_joint: str
    joints: tuple[str, ...]
    control: str
    pole: str
    handle: str
    group: str
    constrained_controls: tuple[str, ...]
    assumed_end: bool


def _short(node):
    return node.rsplit('|', 1)[-1]


def _unique(c, addresses):
    """Generic and RP bindings may spell the same actual DAG object twice."""
    result = {}
    for address in addresses:
        paths = c.ls(address, long=True) or ()
        if len(paths) != 1:
            raise ValueError('QuickIK 原有节点缺失或不唯一：' + address)
        result[paths[0]] = _short(paths[0])
    return tuple(result.values())


def _joint(c, selected, saved):
    """Original inference, with registered Python FK names resolved first."""
    name = _short(selected)
    matched = _unique(c, (joint for joint, control in source_fk_bindings(saved)
                           if source_leaf(control) == source_leaf(selected)))
    if len(matched) > 1:
        raise ValueError('QuickIK 起点控制器对应多个关节：' + selected)
    prefix = ''
    if matched:
        name, prefix = matched[0], 'FK'
    else:
        candidate = name.replace('FK', '', 1)
        if c.objExists(candidate):
            name, prefix = candidate, 'FK'
    candidate = name.replace('_', 'Joint_', 1)
    if c.objExists(candidate):
        name, prefix = candidate, ''
    return name, prefix


def _control(c, joint, prefix, saved):
    if prefix:
        candidates = _unique(c, (control for body, control in source_fk_bindings(saved)
                                 if source_leaf(body) == source_leaf(joint)))
        if len(candidates) > 1:
            raise ValueError('QuickIK 关节对应多个 FK 控制器：' + joint)
        if candidates:
            return candidates[0]
    if ':' in joint:
        tokens = joint.split(':')
        control = tokens[0] + ':' + prefix + tokens[1]
    else:
        control = prefix + joint
    return joint.replace('Joint', '', 1) if prefix == '' else control


def create(host, selection=None):
    host._require_transaction()
    c = host._cmds
    selected = tuple(c.ls(selection=True) or ()) if selection is None else tuple(selection)
    if len(selected) != 2:
        raise ValueError('Select Start control + End control')
    saved = registration(host)
    if saved is not None:
        saved = host.read_character_registration()
    joints, prefix = [], ''
    for control in selected:
        joint, found_prefix = _joint(c, control, saved)
        joints.append(joint)
        # MEL's single ctrlPrefix is assigned only when an inference succeeds.
        if joint != _short(control) or found_prefix:
            prefix = found_prefix
    start = end = ''
    if joints[1] in (c.listRelatives(joints[0], allDescendents=True, type='joint') or ()):
        start, end = joints
    if joints[0] in (c.listRelatives(joints[1], allDescendents=True, type='joint') or ()):
        end, start = joints
    if not start or not end:
        raise ValueError('Unable to find Start & End joint for the IK, make sure to select 2 control that are in the same hierarchy.')
    name = start.replace(':', '_')
    start_parent = c.listRelatives(start, parent=True)[0]
    descendants = c.listRelatives(end, allDescendents=True, type='joint') or ()
    assumed = len(descendants) == 1
    if assumed:
        end = descendants[0]
    path = c.ls(end, long=True)[0]
    reverse = []
    for joint in reversed(tuple(part for part in path.split('|') if part)):
        reverse.append(joint)
        if joint == start:
            break
    chain = tuple(reversed(reverse))
    identity = getattr(c, 'identity', None)
    if identity is not None and any(not identity.owns(host.scene_address(node)) for node in (*selected, *chain)):
        raise ValueError('QuickIK 选择跨越了当前角色命名空间')
    for joint in chain:
        if c.objExists('QuickIKjoint_' + joint):
            raise ValueError('Another QuickIK already using the Joint:"QuickIKjoint_' + joint + '"')
    axis = 'y' if 'Finger' in start else 'z'
    quick = 'QuickIK_' + name
    pole = 'QuickPoleVector_' + name
    group = quick + 'Group'
    handle = quick + 'Handle'
    temporary = tuple('QuickIKjoint_' + joint.replace(':', '_') for joint in chain)
    host._transaction_changed = True
    if not c.objExists('QuickIK'):
        c.createNode('transform', name='QuickIK')
    if c.objExists(group):
        c.delete(group)
    c.createNode('transform', name=group, parent=start)
    c.parent(group, 'QuickIK')
    for index, (joint, copied) in enumerate(zip(chain, temporary)):
        c.select(joint)
        c.joint(name=copied)
        c.setAttr(copied + '.rotateOrder', c.getAttr(joint + '.rotateOrder'))
        if axis == 'y':
            c.setAttr(copied + '.preferredAngle', 0, 10, 0, type='float3')
        if index:
            c.parent(copied, temporary[index - 1])
    c.parent(temporary[0], group)
    c.parentConstraint(start_parent, temporary[0], maintainOffset=True)
    a = c.xform(start, query=True, worldSpace=True, translation=True)
    b = c.xform(end, query=True, worldSpace=True, translation=True)
    distance = dist(a, b)
    c.spaceLocator(name=quick)
    c.parent(quick, group)
    c.setAttr(quick + 'Shape.overrideEnabled', 1)
    c.setAttr(quick + 'Shape.overrideColor', 13)
    c.setAttr(quick + 'Shape.localScale', *(distance / 2 for _ in range(3)), type='float3')
    c.duplicate(quick, name=pole)
    c.setAttr(pole + 'Shape.localScale', *(distance / 4 for _ in range(3)), type='float3')
    c.xform(quick, worldSpace=True, translation=b)
    c.ikHandle(name=handle, numSpans=2, solver='ikRPsolver', startJoint=temporary[0], endEffector=temporary[-1])
    c.parent(handle, quick)
    c.setAttr(handle + '.v', 0)
    c.parent(pole, start)
    c.xform(pole, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0))
    c.setAttr(pole + ('.tz' if axis == 'y' else '.ty'), distance)
    c.poleVectorConstraint(pole, handle)
    shape = c.createNode('annotationShape')
    annotation = 'QuickPoleAnnotation_' + name
    c.rename(c.listRelatives(shape, parent=True)[0], annotation)
    c.setAttr(annotation + 'Shape.overrideEnabled', 1)
    c.setAttr(annotation + 'Shape.overrideDisplayType', 2)
    c.parent(annotation, quick)
    c.xform(annotation, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0))
    c.connectAttr(pole + 'Shape.worldMatrix[0]', annotation + 'Shape.dagObjectMatrix[0]')
    c.setAttr(pole + '.tx', c.getAttr(quick + '.tx'))
    offset = 'QuickIKOffset_' + name
    pole_offset = 'QuickPoleVectorOffset_' + name
    c.createNode('transform', name=offset, parent=quick)
    c.parent(offset, group)
    c.parent(quick, offset)
    c.createNode('transform', name=pole_offset, parent=pole)
    c.parent(pole_offset, quick)
    c.parent(pole, pole_offset)
    controls = []
    constraints = []
    for index, (joint, copied) in enumerate(zip(chain, temporary)):
        if index == len(chain) - 1 and assumed:
            continue
        control = _control(c, joint, prefix, saved)
        if not c.objExists(control):
            c.warning('Could not find controller:"' + control + '"\n')
            continue
        constraints.extend(c.orientConstraint(copied, control))
        controls.append(control)
    c.select(quick)
    if saved is not None:
        from .maya_original_quick_ik_state import remember
        remember(host, group, controls, constraints)
        from .maya_original_export_preparation import MayaOriginalExportPreparationHost
        MayaOriginalExportPreparationHost._remember_export_preparation(host, saved)
    return OriginalQuickIK(start, end, temporary, quick, pole, handle, group, tuple(controls), assumed)


class MayaOriginalQuickIKMixin:
    def create_original_quick_ik(self, selection=None):
        return create(self, selection)
