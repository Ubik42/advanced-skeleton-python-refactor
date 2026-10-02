"""Offline source decisions; these checks do not initialize or emulate Maya."""
from contextlib import contextmanager
import json
from types import SimpleNamespace as Row
import unittest

from adv_py.core.original_control_orientation import (
    AXES, OriginalControlOrientOptions, original_control_identity,
)
from adv_py.core.original_control_mirror import original_mirror_order, original_mirror_sign
from adv_py.core.original_joint_orientation import original_game_joint_rotations
from adv_py.adapters.maya_original_rla_child import original_rla_child, original_non_part_rla_child
from adv_py.adapters.maya_control_orient_registration import (
    _replace_edges, _refresh_sdk_children, detached_sdk_child,
)
from adv_py.application.original_control_orientation import (
    SetOriginalControlOrientations, DetachOriginalControlOrientations,
    AttachOriginalControlOrientations,
)
from adv_py.application.control_orientation import SetControlOrientationAxis


class OriginalOrientationSourceTests(unittest.TestCase):
    def test_game_joint_source_rotation_order_is_two_steps_for_z_x(self):
        self.assertEqual(original_game_joint_rotations('Z', 'X'), ((0.,90.,0.), (0.,0.,90.)))
        self.assertEqual(original_game_joint_rotations('X', 'Y'), ())
        self.assertEqual(original_game_joint_rotations('Y', 'X'), ((0.,180.,-90.),))
        self.assertEqual(original_game_joint_rotations('Y', 'Z'), ((0.,-90.,-90.),))
        self.assertEqual(original_game_joint_rotations('X', 'Z'), ((-90.,0.,0.),))
        self.assertEqual(original_game_joint_rotations('Z', 'Y'), ((0.,90.,0.),))

    def test_game_joint_equal_axes_remain_a_source_error(self):
        with self.assertRaises(ValueError):
            original_game_joint_rotations('Y', 'Y')
    def test_successive_source_prefixes_and_extra(self):
        for role, kind, name, side in (
            ('IKLocalArm_R', 'IKLocal', 'Arm', '_R'),
            ('IKhybridLeg2_L', 'IKhybrid', 'Leg2', '_L'),
            ('BendMidSpine3_M', 'BendMid', 'Spine3', '_M'),
            ('RootX_M', 'Root', 'X', '_M'),
            ('FKExtraWrist_R', 'FKExtra', 'Wrist', '_R'),
        ):
            found = original_control_identity(role)
            self.assertEqual((found.kind, found.name, found.side), (kind, name, side))

    def test_source_tokenize_does_not_take_last_side_token(self):
        found = original_control_identity('|hero:Group|hero:FK__Finger_R_extra')
        self.assertEqual((found.kind, found.name, found.side), ('FK', 'Finger', '_R'))

    def test_all_signed_axis_pairs_use_source_object_up_rule(self):
        count = 0
        for primary in AXES:
            for secondary in AXES:
                if primary[-1] == secondary[-1]:
                    with self.assertRaises(ValueError):
                        OriginalControlOrientOptions(primary, secondary)
                    continue
                aim, up, world = OriginalControlOrientOptions(primary, secondary).aim_vectors()
                self.assertEqual(sum(a*b for a,b in zip(aim, up)), 0.)
                self.assertEqual(world, (0.,0.,1.) if primary[-1] == 'Y' else (0.,1.,0.))
                count += 1
        self.assertEqual(count, 24)

    def test_mirrored_behaviour_reverses_aim_and_up(self):
        options = OriginalControlOrientOptions('-Z', 'X', mirrored_behaviour=True)
        self.assertEqual(options.aim_vectors(reverse=True), ((0.,0.,1.), (-1.,0.,0.), (0.,1.,0.)))

    def test_world_modes_reverse_up_only_and_do_not_rewrite_saved_axes(self):
        for field in ('world_orient', 'world_match'):
            options = OriginalControlOrientOptions('Y', '-X', mirrored_behaviour=True, **{field: True})
            aim, up, _ = options.aim_vectors(reverse=True)
            self.assertEqual((aim, up), ((1.,0.,0.), (0.,0.,-1.)))
            self.assertEqual((options.primary, options.secondary), ('Y', '-X'))

    def test_mirror_order_preserves_original_duplicate_passes(self):
        ordered = original_mirror_order(('FKHand_R', 'IKSpine2_M', 'PoleArm_R',
            'IKhybridLeg2_R', 'IKhybridLeg1_R', 'Main'), stiff=frozenset(('IKSpine2_M',)))
        self.assertEqual(ordered[:5], ('Main', 'RootX_M', 'RootExtraX_M', 'IKhybridLeg1_R', 'IKhybridLeg2_R'))
        self.assertEqual(ordered.count('IKSpine2_M'), 2)
        self.assertLess(ordered.index('IKSpine2_M'), ordered.index('PoleArm_R'))

    def test_old_fk_translation_and_other_rotation_signs(self):
        self.assertEqual(original_mirror_sign('FKWrist_R', 'tx'), -1.)
        self.assertEqual(original_mirror_sign('FKWrist_R', 'rx'), 1.)
        self.assertEqual(original_mirror_sign('IKArm_R', 'ry'), -1.)
        self.assertEqual(original_mirror_sign('IKArm_R', 'rz'), 1.)

    def test_z_minus_y_local_ik_custom_and_face_branches(self):
        self.assertEqual(original_mirror_sign('IKArm_R', 'rz', axes_z_minus_y=True), -1.)
        self.assertEqual(original_mirror_sign('IKArm_R', 'tx', ik_local=True), -1.)
        self.assertEqual(original_mirror_sign('ctrlCustom_R', 'tz', local_custom=True), -1.)
        self.assertEqual(original_mirror_sign('FKWrist_R', 'tx', positive_scale=False), 1.)
        self.assertEqual(original_mirror_sign('FKWrist_R', 'tx', face=True), 1.)

    def test_rla_first_same_side_and_last_preferred_child(self):
        positions = {'Ankle_R':(-1.,0.,0.), 'First_R':(-2.,0.,0.),
                     'Toes1_R':(-3.,0.,0.), 'Toes2_R':(-4.,0.,0.)}
        c = Row(objExists=lambda _:False,
            xform=lambda node, **_:positions[node],
            listRelatives=lambda *_, **__:['First_R','Toes1_R','Toes2_R'])
        self.assertEqual(original_rla_child(c, 'Ankle_R'), 'Toes2_R')

    def test_rla_strict_center_boundary_uses_fit_scale(self):
        c = Row(objExists=lambda _:True, getAttr=lambda _:2.,
            xform=lambda node, **_: (.02 if node == 'Joint_R' else .01, 0.,0.),
            listRelatives=lambda *_, **__:['Child_M'])
        self.assertEqual(original_rla_child(c, 'Joint_R'), '')

    def test_non_part_child_uses_reversed_native_descendant_order(self):
        def relatives(node, **flags):
            return ['End_R','Near_R'] if flags.get('allDescendents') else ['JointPart1_R']
        c = Row(objExists=lambda _:False, xform=lambda *_, **__:(-1.,0.,0.), listRelatives=relatives)
        self.assertEqual(original_non_part_rla_child(c, 'Joint_R'), 'Near_R')

    def test_only_replaced_inbetween_input_edge_changes(self):
        source = {'nodes':[{'name':'Matrix', 'connections':[
            ['Extra.parentInverseMatrix[0]', 'matrixIn[0]'],
            ['Other.parentInverseMatrix[0]', 'matrixIn[1]']]}],
            'notes':'Extra.parentInverseMatrix[0]'}
        updated = _replace_edges(source, {('Extra.parentInverseMatrix[0]', 'Matrix.matrixIn[0]'):
                                         'Offset.worldInverseMatrix[0]'})
        self.assertEqual(updated['nodes'][0]['connections'][0][0], 'Offset.worldInverseMatrix[0]')
        self.assertEqual(updated['nodes'][0]['connections'][1], source['nodes'][0]['connections'][1])
        self.assertEqual(updated['notes'], source['notes'])
        self.assertEqual(source['nodes'][0]['connections'][0][0], 'Extra.parentInverseMatrix[0]')


class SourceHost:
    def __init__(self, proceed=1):
        self.proceed = proceed
        self.calls = []
    @contextmanager
    def transaction(self, label):
        self.calls.append(('begin', label))
        yield
        self.calls.append(('end', label))
    def confirm_original_control_build_pose(self):
        self.calls.append(('confirm',))
        return self.proceed
    def set_original_control_orientation(self, controls, options):
        self.calls.append(('set', controls, options))
        return ('|CustomOrientFKWrist_R|Wrist',)
    def detach_original_control_orientation(self):
        self.calls.append(('detach',))
        return ('Wrist',)
    def attach_original_control_orientation(self, *, mirror):
        self.calls.append(('attach', mirror))
        return 1
    def capture_control_orientations(self, controls):
        return tuple(Row(control=control) for control in controls)


class OriginalOrientationApplicationTests(unittest.TestCase):
    def test_cancelled_set_does_not_mutate_controls(self):
        host = SourceHost(0)
        self.assertEqual(SetOriginalControlOrientations(host).apply(('Wrist',), OriginalControlOrientOptions()), ())
        self.assertEqual([call[0] for call in host.calls], ['begin','confirm','end'])

    def test_options_pass_unchanged_to_native_host(self):
        host = SourceHost()
        options = OriginalControlOrientOptions('Y', '-Z', mirrored_translate=True)
        result = SetOriginalControlOrientations(host).apply(('Wrist',), options)
        self.assertEqual(result, ('|CustomOrientFKWrist_R|Wrist',))
        self.assertIs(host.calls[2][2], options)

    def test_existing_axis_application_uses_native_source_host(self):
        host = SourceHost()
        result = SetControlOrientationAxis(host).apply(('Wrist',), 'Z', '-X')
        self.assertIsNone(result.plan)
        self.assertEqual(result.verified[0].control, '|CustomOrientFKWrist_R|Wrist')
        self.assertEqual(host.calls[2][2].primary, 'Z')

    def test_detach_cancel_and_attach_mirror_option(self):
        host = SourceHost(0)
        self.assertEqual(DetachOriginalControlOrientations(host).apply(), ())
        self.assertFalse(any(call[0] == 'detach' for call in host.calls))
        host = SourceHost()
        self.assertEqual(AttachOriginalControlOrientations(host).apply(mirror=False), 1)
        self.assertEqual(host.calls[1], ('attach', False))


class SdkFrameCommands:
    """Record parent/identity facts only; no transform computation is mocked."""
    def __init__(self):
        self.parents = {'|SDK':None, '|SDK|CustomOrientFKWrist_R':'|SDK',
                        '|SDK|CustomOrientFKWrist_R|Extra':'|SDK|CustomOrientFKWrist_R'}
        self.identities = {'sdk-id':'|SDK', 'member-id':'|SDK|CustomOrientFKWrist_R|Extra'}
        self.aliases = {}
        self.values = {'|SDK.advPySourceDrivingSDK':json.dumps(dict(
            child='|SDK|CustomOrientFKWrist_R|Extra', scale=None))}
        self.writes = []
    def objExists(self, node):
        return node in self.parents or node in self.values
    def listRelatives(self, node, **_):
        parent = self.parents[node]
        return [parent] if parent else []
    def ls(self, node, **flags):
        if flags.get('uuid'):
            return [next(identity for identity, path in self.identities.items() if path == node)]
        return [self.identities.get(node, self.aliases.get(node, node))] if node in self.identities or node in self.parents else []
    def getAttr(self, plug, **flags):
        return True if flags.get('lock') else self.values[plug]
    def setAttr(self, plug, *values, **flags):
        if values:
            self.values[plug] = values[0]
            self.writes.append((plug, values[0]))


class ExistingSdkOrientationTests(unittest.TestCase):
    def test_sdk_records_new_direct_custom_orient_without_replacing_scale(self):
        c = SdkFrameCommands()
        _refresh_sdk_children(Row(_cmds=c), (Row(path='|SDK'),))
        record = json.loads(c.values['|SDK.advPySourceDrivingSDK'])
        self.assertEqual(record, dict(child='|SDK|CustomOrientFKWrist_R', scale=None))

    def test_detached_sdk_requires_recorded_original_parent_and_member_identity(self):
        c = SdkFrameCommands()
        root = '|asControlOrientDetachParentHolder'
        holder, member = root + '|MatrixHolder', root + '|MatrixHolder|Extra'
        c.parents.update({root:None, holder:root, member:holder})
        c.identities.update({'member-id':member, 'holder-id':holder})
        c.values['asControlOrientDetachParentHolder.advPySourceControlOrientSession'] = json.dumps(
            dict(version=1, rows=[dict(control='control-id',member='member-id',previous='sdk-id',
                holder='holder-id',role='FKWrist_R',reverse=None)]))
        # Scoped commands accept the same logical root name as Maya cmds.
        c.parents['asControlOrientDetachParentHolder'] = None
        c.aliases['asControlOrientDetachParentHolder'] = root
        host = Row(_cmds=c)
        self.assertTrue(detached_sdk_child(host, '|SDK', member))
        c.parents[member] = root
        self.assertFalse(detached_sdk_child(host, '|SDK', member))


if __name__ == '__main__':
    unittest.main()
