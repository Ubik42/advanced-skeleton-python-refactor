"""Native asUnrealTwistJointsBehaviour, ADV 6.925 MEL 62749–62861."""
from adv_py.core.original_game_hierarchy import (
    original_part_joint, original_part_number, original_twist_base,
)
from adv_py.core.character_registry import canonical, safe_json, exact, CharacterRegistryError
from .maya_custom_controller import MayaCustomControllerHost
from .maya_original_control_identity import leaf
from .maya_original_control_orient import _path, _uuid, _by_uuid, _parent
from .maya_game_registration import source_registration, refresh_hierarchy, scene_ids, remember_generated_nodes

MARKER = 'advPySourceUnrealTwist'
IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.)


class MayaUnrealTwistHost(MayaCustomControllerHost):
    def __init__(self, *, namespace=None):
        super().__init__(namespace=namespace, face=False)

    def preflight_twist(self, enable):
        c = self._cmds
        self._unique('DeformationSystem', 'transform')
        if c.objExists('FitSkeleton.useOffsetParentMatrix') and c.getAttr('FitSkeleton.useOffsetParentMatrix'):
            raise ValueError('原版 OPM 角色不能切换 Unreal Twist 关节层级')
        if not enable:
            for joint in self._deform_joints():
                if c.objExists(joint + '.originalParent'):
                    _path(c, c.getAttr(joint + '.originalParent'))

    def _deform_joints(self):
        c = self._cmds
        return c.listRelatives(self._unique('DeformationSystem', 'transform'),
                               allDescendents=True, type='joint', fullPath=True) or []

    def set_twist_hierarchy(self, enable):
        self._require_transaction()
        c = self._cmds
        before = source_registration(self)
        ids_before = scene_ids(self)
        # Native allDescendents order is retained; UUIDs survive each reparent.
        joints = tuple(_uuid(c, node) for node in self._deform_joints())
        count = 0
        for identity in joints:
            joint = _by_uuid(self, identity)
            if not enable:
                if not c.objExists(joint + '.originalParent'):
                    continue
                previous = c.getAttr(joint + '.originalParent')
                self._transaction_changed = True
                c.parent(joint, previous, absolute=True)
                joint = _by_uuid(self, identity)
                c.deleteAttr(joint, attribute='originalParent')
                part = original_part_number(leaf(joint))
                if part > 1:
                    source = c.connectionInfo(joint + '.offsetParentMatrix', sourceFromDestination=True)
                    if source:
                        c.disconnectAttr(source, joint + '.offsetParentMatrix')
                        c.setAttr(joint + '.offsetParentMatrix', *IDENTITY, type='matrix')
                        matrix = leaf(joint) + 'UnrealTwistAccumulate'
                        if c.objExists(matrix):
                            c.delete(matrix)
                if c.objExists(joint + '.' + MARKER):
                    c.setAttr(joint + '.' + MARKER, lock=False)
                    c.deleteAttr(joint, attribute=MARKER)
                count += 1
                continue
            parent = _parent(c, joint)
            depth = 0
            while parent and original_part_joint(leaf(parent)):
                parent = _parent(c, parent)
                depth += 1
            if depth < 1:
                continue
            previous = _parent(c, joint)
            base, side = original_twist_base(leaf(parent))
            if c.objExists(base + '.inbetweenJoints'):
                continue
            part = original_part_number(leaf(joint))
            part_one = None
            self._transaction_changed = True
            if part > 1:
                part_one = _path(c, base + 'Part1' + side)
                # The source samples this matrix even though its variable is
                # not used by the subsequent native accumulation branch.
                if c.objExists('tempMatrixXform'):
                    c.delete('tempMatrixXform')
                sample = c.createNode('transform', name='tempMatrixXform', parent=joint)
                sample = c.parent(sample, part_one, absolute=True)[0]
                c.getAttr(sample + '.matrix')
                c.delete(sample)
            previous_id = _uuid(c, previous)
            parent_id = _uuid(c, parent)
            part_one_id = _uuid(c, part_one) if part_one else None
            c.parent(joint, parent, absolute=True)
            joint = _by_uuid(self, identity)
            if original_part_joint(leaf(joint)):
                c.reorder(joint, relative=-1)
            if not c.objExists(joint + '.originalParent'):
                c.addAttr(joint, longName='originalParent', dataType='string')
            # MEL listRelatives saves the short joint name. Saving the old DAG
            # path would make restoration fail after its Part parent moves.
            c.setAttr(joint + '.originalParent', leaf(previous), type='string')
            matrix = None
            if part == 2:
                c.connectAttr(_by_uuid(self, part_one_id) + '.matrix', joint + '.offsetParentMatrix')
            if part > 2:
                matrix = c.createNode('multMatrix', name=leaf(joint) + 'UnrealTwistAccumulate')
                for index in range(part - 1):
                    c.connectAttr(_by_uuid(self, part_one_id) + '.matrix', matrix + '.matrixIn[' + str(index) + ']')
                c.connectAttr(matrix + '.matrixSum', joint + '.offsetParentMatrix')
            if not c.objExists(joint + '.' + MARKER):
                c.addAttr(joint, longName=MARKER, dataType='string')
            c.setAttr(joint + '.' + MARKER, canonical(dict(
                joint=identity, previous=previous_id, parent=parent_id,
                part=part, part_one=part_one_id, matrix=matrix)), type='string', lock=True)
            count += 1
        refresh_hierarchy(self, before)
        remember_generated_nodes(self, ids_before)
        c.select(clear=True)
        return count


def audit_registered(host, registration):
    c = host._cmds
    for node in registration.nodes:
        plug = node.path + '.' + MARKER
        if not c.objExists(plug):
            continue
        if not c.getAttr(plug, lock=True):
            raise CharacterRegistryError('Unreal Twist 来源登记已解锁')
        row = exact(safe_json(c.getAttr(plug)), ('joint', 'previous', 'parent', 'part', 'part_one', 'matrix'))
        if (_by_uuid(host, row['joint']) != node.path
                or _parent(c, node.path) != _by_uuid(host, row['parent'])
                or c.getAttr(node.path + '.originalParent') != leaf(_by_uuid(host, row['previous']))):
            raise CharacterRegistryError('Unreal Twist 原关节或父级身份变化')
        part = row['part']
        if type(part) is not int or part != original_part_number(leaf(node.path)):
            raise CharacterRegistryError('Unreal Twist 原 Part 编号变化')
        if part < 2:
            continue
        source = _by_uuid(host, row['part_one']) + '.matrix'
        if part == 2:
            valid = row['matrix'] is None and c.isConnected(source, node.path + '.offsetParentMatrix')
        else:
            matrix = row['matrix']
            valid = (c.objExists(matrix) and c.nodeType(matrix) == 'multMatrix'
                     and c.getAttr(matrix + '.matrixIn', multiIndices=True) == list(range(part - 1))
                     and all(c.isConnected(source, matrix + '.matrixIn[' + str(index) + ']') for index in range(part - 1))
                     and c.isConnected(matrix + '.matrixSum', node.path + '.offsetParentMatrix'))
        if not valid:
            raise CharacterRegistryError('Unreal Twist 原累乘矩阵接线变化')
