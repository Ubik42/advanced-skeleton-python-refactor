"""Offline source branch checks; these do not execute or emulate Maya."""
from dataclasses import asdict, replace
import json
import unittest

from adv_py.core.body_game_root_motion import GameRootMotionInput, plan_game_root_motion
from adv_py.core.body_parent_constraint import _node_stem
from adv_py.core.original_game_hierarchy import original_part_number, original_part_joint
from adv_py.core.body_game_scaling import GameScalingJointState, plan_body_game_scaling, audit_body_game_scaling
from adv_py.core.original_game_scaling_record import decode, encode, map_addresses, remap_record, mark_retired, replace_joint_uuids
from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.character_registry import CharacterRegistryError


class OriginalGameEngineTests(unittest.TestCase):
    def root_input(self, height=100.):
        return GameRootMotionInput('|Group|DeformationSystem', '|Group|MotionSystem|RootSystem',
            '|Group|MotionSystem|MainSystem', '|Group|MotionSystem|MainSystem|Main',
            '|Group|MotionSystem|ConstraintSystem', '|Group|DeformationSystem|Root_M',
            'ControlSet', '|Group|MotionSystem|buildPose', '', height, True, False)

    def test_source_height_has_no_minimum_radius(self):
        self.assertEqual(plan_game_root_motion(self.root_input(0.), create=True).radius, 0.)
        self.assertEqual(plan_game_root_motion(self.root_input(.1), create=True).radius, .005)

    def test_source_legacy_root_names(self):
        plan = plan_game_root_motion(replace(self.root_input(), root_joint_name='root'), create=True)
        self.assertEqual(plan.joint_path, '|Group|DeformationSystem|root')
        self.assertEqual(plan.control_path.rsplit('|', 1)[-1], 'FKroot')
        self.assertEqual(plan.matrix_name, 'rootMM_root')

    def test_root_motion_moves_the_direct_export_wrapper(self):
        source = self.root_input()
        wrapper = source.deformation + '|UnrealRoot'
        source = replace(source, body_root=wrapper + '|Root_M', deformation_children=(wrapper,))
        created = plan_game_root_motion(source, create=True)
        self.assertEqual(created.body_path, created.joint_path + '|UnrealRoot|Root_M')
        removed = plan_game_root_motion(replace(source, exists=True,
            body_root=created.body_path, deformation_children=(created.joint_path + '|UnrealRoot',)), create=False)
        self.assertEqual(removed.body_path, source.body_root)

    def test_delete_empty_root_motion_leaves_unreal_branch(self):
        source = self.root_input()
        source = replace(source, exists=True, body_root=source.deformation + '|UnrealRoot|Root_M',
            deformation_children=())
        self.assertEqual(plan_game_root_motion(source, create=False).body_path, source.body_root)

    def test_both_native_root_names_can_wrap_each_other(self):
        source = self.root_input()
        legacy = source.deformation + '|root'
        source = replace(source, body_root=legacy + '|Root_M', deformation_children=(legacy,))
        plan = plan_game_root_motion(source, create=True)
        self.assertEqual(plan.body_path, source.deformation + '|RootMotion_M|root|Root_M')

    def test_delete_modern_root_nested_below_legacy_root(self):
        source = self.root_input()
        joint = source.deformation + '|root|RootMotion_M'
        source = replace(source, exists=True, root_joint_path=joint,
            body_root=joint + '|Root_M', deformation_children=(joint + '|Root_M',))
        plan = plan_game_root_motion(source, create=False)
        self.assertEqual(plan.joint_path, joint)
        self.assertEqual(plan.body_path, source.deformation + '|Root_M')

    def test_source_parent_constraint_tokenization(self):
        self.assertEqual(_node_stem('|Group|root'), ('root', '_root'))
        self.assertEqual(_node_stem('|Group|Other_custom'), ('Other', '_custom'))
        self.assertEqual(_node_stem('Body__R'), ('Body', '_R'))

    def test_source_part_pattern_is_not_anchored_at_suffix(self):
        self.assertTrue(original_part_joint('LegPart2Extra_R'))
        self.assertEqual(original_part_number('LegPart2Extra_R'), 0)
        self.assertEqual(original_part_number('ArmPart2Part3_R'), 3)
        self.assertEqual(original_part_number('Root_M'), 0)

    def state(self, name, parent=None, **kwargs):
        return GameScalingJointState(path=name, parent=parent, segment_scale_compensate=True,
            has_marker=False, scale_sources=('FK.scaleX', 'FK.scaleY', 'FK.scaleZ'),
            stored_sources=(None, None, None), **kwargs)

    def test_original_nearest_fk_skips_the_direct_parent(self):
        root = self.state('|D|Root_M', fk_control_exists=True)
        parent = self.state('|D|Root_M|LegPart1_R', root.path, fk_control_exists=True)
        child = self.state('|D|Root_M|LegPart1_R|Leg_R', parent.path)
        plan = plan_body_game_scaling((child, parent, root), enable=True)
        inverse = next(node for node in plan.nodes if node.name == 'GameEngineScalingSSCMPD1Leg_R')
        self.assertEqual(inverse.input2_sources, root.scale_sources)
        part = next(row for row in plan.joints if row.path == parent.path)
        self.assertIsNone(part.compensation_node)

    def test_ancestor_without_native_stored_scale_has_no_inverse_input(self):
        root = replace(self.state('|D|Other_M', fk_control_exists=True), segment_scale_compensate=False)
        part = self.state(root.path + '|LegPart1_R', root.path)
        child = self.state(part.path + '|Leg_R', part.path)
        plan = plan_body_game_scaling((child, part, root), enable=True)
        inverse = next(node for node in plan.nodes if node.name == 'GameEngineScalingSSCMPD1Leg_R')
        self.assertEqual(inverse.input2_sources, (None, None, None))

    def test_native_fk_follow_routes_are_retained_when_disabled(self):
        path = '|D|Root_M'
        stored = ('FK.scaleX', 'FK.scaleY', 'FK.scaleZ')
        follow = tuple(path + '.GameEngineScalingS' + axis for axis in 'XYZ')
        before = GameScalingJointState(path, None, False, True,
            tuple('GameEngineScalingSSCMPD2Root_M.output' + axis for axis in 'XYZ'), stored,
            stored_attributes=(True, True, True), fk_parent_constraint='FKParentConstraintToRoot_M',
            fk_parent_scale_sources=follow, uuid='body-identity')
        plan = plan_body_game_scaling((before,), enable=False)
        after = replace(before, segment_scale_compensate=True, scale_sources=stored)
        self.assertEqual(audit_body_game_scaling(plan, (before,), (after,)), ())
        wrong = replace(after, fk_parent_scale_sources=stored)
        self.assertTrue(audit_body_game_scaling(plan, (before,), (wrong,)))

    def test_deleted_export_joint_record_keeps_native_scaling_nodes(self):
        before = (self.state('|D|Root_M'), self.state('|D|UnrealRoot'))
        plan = plan_body_game_scaling(before, enable=True)
        retired = replace(plan, retired_joints=('|D|UnrealRoot',))
        text = json.dumps(dict(version=1, before=[asdict(row) for row in before], plan=asdict(retired)))
        self.assertEqual(decode(text), (before, retired))
        self.assertEqual(retired.nodes, plan.nodes)

    def test_unreal_left_hand_is_parented_to_gun(self):
        from adv_py.core.unreal_joints import plan_unreal_joints
        for legacy in (True, False):
            plan = plan_unreal_joints(has_root_motion=legacy, opm=False, landmarks={})
            parents = {row.name: row.parent for row in plan.joints}
            self.assertEqual(parents['ik_hand_l'], 'ik_hand_gun')
            self.assertEqual(parents['ik_hand_r'], 'ik_hand_gun')
            self.assertEqual(parents['ik_hand_root'], 'root' if legacy else 'UnrealRoot')

    def test_unreal_rename_reuses_right_counts_for_left_side(self):
        from adv_py.core.unreal_rename import plan_unreal_rename
        plan = plan_unreal_rename(('Root_M', 'Chest_M', 'KneePart1_R', 'KneePart2_R',
            'KneePart1_L'), ('Chest_M',))
        self.assertEqual(dict(plan.names)['KneePart1_L'], 'calf_twist_02_l')
        self.assertEqual(plan.right_knee_parts, 2)

    def test_partial_axis_reroute_removes_the_whole_fk_compound_edge(self):
        path = '|D|Root_M'
        before = GameScalingJointState(path, None, True, False, ('FK.scaleX', None, None),
            (None, None, None), fk_parent_constraint='FKParentConstraintToRoot_M',
            fk_parent_scale_sources=tuple(path + '.scale' + axis for axis in 'XYZ'),
            fk_parent_compound_scale_source=path + '.scale')
        plan = plan_body_game_scaling((before,), enable=True)
        after = replace(before, segment_scale_compensate=False, has_marker=True,
            stored_attributes=(True, False, False), stored_sources=('FK.scaleX', None, None),
            scale_sources=('GameEngineScalingSSCMPD2Root_M.outputX', None, None),
            fk_parent_scale_sources=(path + '.GameEngineScalingSX', None, None),
            fk_parent_compound_scale_source=None)
        self.assertEqual(audit_body_game_scaling(plan, (before,), (after,)), ())

    def test_source_is_in_ik_lives_across_empty_joint_iterations(self):
        root = self.state('|D|Root_M', fk_control_exists=True)
        ik = GameScalingJointState('|D|Root_M|IK_R', root.path, True, True,
            (None, None, None), ('ScaleBlendIK.outputR', None, None),
            stored_attributes=(True, False, False))
        empty = GameScalingJointState('|D|Root_M|IK_R|End_R', ik.path, True, True,
            (None, None, None), (None, None, None), stored_attributes=(True, False, False))
        plan = plan_body_game_scaling((ik, empty, root), enable=True)
        self.assertIsNotNone(next(row for row in plan.joints if row.path == empty.path).parent_inverse_node)

    def test_repeat_enable_does_not_capture_deleted_compensation_output(self):
        row = GameScalingJointState('|D|Root_M', None, False, True,
            tuple('GameEngineScalingSSCMPD2Root_M.output' + axis for axis in 'XYZ'),
            ('FK.scaleX', 'FK.scaleY', 'FK.scaleZ'), stored_attributes=(True, True, True))
        plan = plan_body_game_scaling((row,), enable=True)
        self.assertTrue(all(axis.disconnect_scale_source is None for axis in plan.joints[0].axes))
        self.assertEqual(plan.nodes[0].input1_sources, row.stored_sources)
        restored = plan_body_game_scaling((row,), enable=False)
        self.assertEqual(tuple(axis.restore_source for axis in restored.joints[0].axes), row.stored_sources)

    def test_record_addresses_roundtrip_without_rewriting_axis_labels(self):
        before = (self.state('|D|Root_M'),)
        plan = plan_body_game_scaling(before, enable=True)
        identity = CharacterIdentity('hero')
        physical_before, physical_plan = map_addresses(before, plan, identity.to_scene)
        local_before, local_plan = map_addresses(physical_before, physical_plan, identity.to_local)
        self.assertEqual((local_before, local_plan), (before, plan))
        self.assertEqual(physical_plan.joints[0].axes[0].axis, 'X')
        text = json.dumps(dict(version=1, before=[asdict(row) for row in before], plan=asdict(plan)))
        self.assertEqual(decode(text), (before, plan))

    def test_record_rejects_a_different_business_branch(self):
        before = (self.state('|D|Root_M'),)
        plan = plan_body_game_scaling(before, enable=True)
        record = dict(version=1, before=[asdict(row) for row in before], plan=asdict(plan))
        record['plan']['nodes'][0]['operation'] = 2
        with self.assertRaises(CharacterRegistryError):
            decode(json.dumps(record))

    def test_moving_part_hierarchy_preserves_the_earlier_scaling_branch(self):
        root = self.state('|D|Root_M', fk_control_exists=True, uuid='root')
        part = self.state(root.path + '|ArmPart1_R', root.path, uuid='part')
        end = self.state(part.path + '|Hand_R', part.path, uuid='hand')
        before = (end, part, root)
        plan = plan_body_game_scaling(before, enable=True)
        self.assertIsNotNone(plan.joints[0].parent_inverse_node)
        moved = root.path + '|Hand_R'
        def convert(address):
            return moved + address[len(end.path):] if address == end.path or address.startswith(end.path + '.') else address
        text = remap_record(encode(before, plan), convert)
        current, restored = decode(text)
        self.assertEqual(restored, map_addresses(before, plan, convert)[1])
        # A fresh invocation after reparenting is deliberately a different
        # native operation; the saved earlier graph must not turn into it.
        fresh = (replace(current[0], parent=root.path), current[1], current[2])
        self.assertIsNone(plan_body_game_scaling(fresh, enable=True).joints[0].parent_inverse_node)
        self.assertIsNotNone(restored.joints[0].parent_inverse_node)

    def test_root_wrapper_does_not_recalculate_the_saved_ancestor_search(self):
        root = self.state('|D|Root_M', fk_control_exists=True)
        part = self.state(root.path + '|ArmPart1_R', root.path)
        hand = self.state(part.path + '|Hand_R', part.path)
        before = (hand, part, root)
        plan = plan_body_game_scaling(before, enable=True)
        def convert(address):
            return address.replace('|D|Root_M', '|D|RootMotion_M|Root_M', 1)
        restored = decode(remap_record(encode(before, plan), convert))[1]
        self.assertEqual(restored.nodes, map_addresses(before, plan, convert)[1].nodes)

    def test_frozen_scaling_record_composes_namespace_and_hierarchy_handoffs(self):
        before = (self.state('|D|Root_M', uuid='original'),)
        plan = plan_body_game_scaling(before, enable=True)
        text = remap_record(encode(before, plan), CharacterIdentity('stage').to_scene)
        text = remap_record(text, CharacterIdentity('stage').to_local)
        self.assertEqual(decode(text), (before, plan))
        self.assertEqual(json.loads(text)['basis']['before'][0]['uuid'], 'original')

    def test_retirement_keeps_the_calculation_basis_and_orphan_nodes(self):
        before = (self.state('|D|Root_M', uuid='body'), self.state('|D|UnrealRoot', uuid='deleted'))
        plan = plan_body_game_scaling(before, enable=True)
        text = mark_retired(encode(before, plan), {'|D|UnrealRoot'})
        text = replace_joint_uuids(text, {'|D|Root_M': 'replacement-body'})
        current, restored = decode(text)
        self.assertEqual(restored.retired_joints, ('|D|UnrealRoot',))
        self.assertEqual(restored.nodes, plan.nodes)
        self.assertEqual(current[0].uuid, 'replacement-body')
        self.assertEqual(current[1].uuid, 'deleted')

    def test_frozen_record_rejects_addressing_two_joints_as_one(self):
        before = (self.state('|D|Root_M'), self.state('|D|Hip_R'))
        text = encode(before, plan_body_game_scaling(before, enable=True))
        with self.assertRaises(CharacterRegistryError):
            remap_record(text, lambda node: '|D|Root_M' if node == '|D|Hip_R' else node)

    def test_stored_unconnected_scale_constant_is_retained(self):
        from adv_py.core.body_game_scaling import game_scaling_result_states
        before = replace(self.state('|D|Root_M'), has_marker=True,
            stored_attributes=(True, False, False), stored_values=(2.5, 0., 0.))
        plan = plan_body_game_scaling((before,), enable=False)
        result = game_scaling_result_states((before,), plan)
        self.assertEqual(result[0].stored_values[0], 2.5)
        self.assertEqual(audit_body_game_scaling(plan, (before,), result), ())
        self.assertTrue(audit_body_game_scaling(plan, (before,), (replace(result[0], stored_values=(0., 0., 0.)),)))

    def test_mannequin_native_constraints_match_source_order(self):
        from adv_py.core.unreal_mannequin import plan_mannequin
        matches = plan_mannequin().matches
        names = [row.source for row in matches]
        self.assertEqual(names[:4], ['rootUserCreated', 'Root_M', 'Chest_M', 'Scapula_R'])
        self.assertEqual(names[names.index('PinkyFinger1_R'):names.index('PinkyFinger1_R') + 6],
            ['PinkyFinger1_R', 'RingFinger1_R', 'MiddleFinger1_R', 'IndexFinger1_R', 'ThumbFinger1_R', 'PinkyFinger2_R'])
        self.assertLess(names.index('ThumbFinger3_R'), names.index('Hip_R'))
        self.assertLess(names.index('Toes_L'), names.index('Neck_M'))
        self.assertLess(names.index('Head_M'), names.index('hand_r'))
        self.assertTrue(next(row for row in matches if row.source == 'Toes_R').maintain_orientation)
        self.assertTrue(all(not row.maintain_position for row in matches))

    def test_mannequin_360_correction_has_source_strict_thresholds(self):
        from adv_py.core.unreal_mannequin import native_orient_offset
        self.assertEqual(native_orient_offset(181, 180), -180)
        self.assertEqual(native_orient_offset(-181, -180), 180)
        self.assertEqual(native_orient_offset(180, 180), 180)
        self.assertEqual(native_orient_offset(181, 179), 179)
        self.assertEqual(native_orient_offset(-180, -180), -180)
        self.assertEqual(native_orient_offset(-181, -179), -179)

    def test_unreal_rename_starts_with_spine_then_original_known_table(self):
        from adv_py.core.unreal_rename import plan_unreal_rename
        source = ('Custom_M', 'IndexFinger1_L', 'ElbowPart1_R', 'Neck_M',
                  'ShoulderPart1_R', 'KneePart1_R', 'HipPart1_R', 'Root_M', 'Chest_M')
        plan = plan_unreal_rename(source, ('Chest_M',))
        self.assertEqual([row[0] for row in plan.names[:7]],
            ['Chest_M', 'Root_M', 'Neck_M', 'HipPart1_R', 'KneePart1_R', 'ShoulderPart1_R', 'ElbowPart1_R'])
        self.assertEqual(plan.known_names[-1], 'IndexFinger1_L')
        self.assertEqual(plan.names[-1], ('Custom_M', 'Custom'))


class OriginalExportRulesTests(unittest.TestCase):
    def test_preset_edits_only_native_five_options_and_preserves_bytes(self):
        from adv_py.core.original_fbx_export import source_fbx_preset
        xml = (b'\xef\xbb\xbf<Settings>\r\n<PresetSelected v="UE"/>\r\n'
               b'<BakeComplexAnimation v="0"/>\r\n<BakeFrameStep v="4"/>\r\n'
               b'<InputConnections v="1"/>\r\n<IncludeChildren v="0"/>\r\n'
               b'<Other v="9"/>\r\n</Settings>')
        expected = (b'\xef\xbb\xbf<Settings>\r\n<PresetSelected v=""/>\r\n'
                    b'<BakeComplexAnimation v="1"/>\r\n<BakeFrameStep v="1"/>\r\n'
                    b'<InputConnections v="0"/>\r\n<IncludeChildren v="1"/>\r\n'
                    b'<Other v="9"/>\r\n</Settings>')
        self.assertEqual(source_fbx_preset(xml), expected)

    def test_preset_uses_source_first_value_on_matching_line(self):
        from adv_py.core.original_fbx_export import source_fbx_preset
        self.assertEqual(source_fbx_preset(b'<Other v="9"/><BakeFrameStep v="4"/>\n'),
                         b'<Other v="1"/><BakeFrameStep v="4"/>\n')

    def test_preset_requires_source_element_space(self):
        from adv_py.core.original_fbx_export import source_fbx_preset
        value = b'<BakeFrameStepExtra v="4"/>\n<BakeFrameStep\tv="4"/>\n'
        self.assertEqual(source_fbx_preset(value), value)

    def test_mannequin_export_defaults_and_namespace_rules(self):
        from adv_py.core.original_fbx_export import MannequinExportOptions
        options = MannequinExportOptions()
        self.assertEqual(options.template, 'UE5 (Simple)')
        self.assertTrue(options.scale_adv_to_template and options.match_template_pose and options.remove_unused_joints)
        self.assertFalse(options.keep_joints)
        self.assertEqual(MannequinExportOptions(namespace='character:export').namespace, 'character:export')
        for namespace in (':rig', 'rig:', 'rig::export', 'rig name'):
            with self.subTest(namespace=namespace), self.assertRaises(ValueError):
                MannequinExportOptions(namespace=namespace)
        with self.assertRaises(ValueError):
            MannequinExportOptions(keep_joints=1)

    def test_face_filename_checks_last_path_separator_and_json_case(self):
        from adv_py.core.unreal_face_solver import face_solver_filename
        self.assertEqual(face_solver_filename(r'C:\my.folder\hero'), r'C:\my.folder\hero_FaceRig.json')
        self.assertEqual(face_solver_filename('/folder.v2/hero.FBX'), '/folder.v2/hero_FaceRig.json')
        self.assertEqual(face_solver_filename('/hero.JSON'), '/hero.JSON')
        self.assertEqual(face_solver_filename('/hero_facerig.fbx'), '/hero_facerig.json')
        self.assertEqual(face_solver_filename(''), '')

    def test_face_sample_order_keeps_out_of_range_neutral(self):
        from adv_py.core.unreal_face_solver import sample_values
        self.assertEqual(sample_values(-2., 2., 3.), (-2., 0., 3., 2.))
        self.assertEqual(sample_values(1., 2., 1.5), (1., 1.5, 2.))
        self.assertEqual(sample_values(-1., 1., 0.), (-1., 0., 1.))

    def test_face_sample_uniqueness_has_strict_native_threshold(self):
        from adv_py.core.unreal_face_solver import sample_values
        self.assertEqual(sample_values(0., 0., .0001), (0., .0001))
        self.assertEqual(sample_values(0., 0., .00009), (0.,))

    def test_middle_lid_uses_highest_index_and_prefers_lower_gap(self):
        from adv_py.core.unreal_face_solver import middle_lid_index
        self.assertEqual(middle_lid_index((0, 3, 5, 8)), 3)
        self.assertEqual(middle_lid_index((0, 4, 8)), 4)
        self.assertEqual(middle_lid_index((0, 99, 100)), 0)
        self.assertIsNone(middle_lid_index((-1, 100)))

    def test_face_channel_names_preserve_driver_translation_semantics(self):
        from adv_py.core.unreal_face_solver import channel_name
        self.assertEqual(channel_name('tx'), 'Translation.X')
        self.assertEqual(channel_name('translateY', driver=True), 'Value.Y')
        self.assertEqual(channel_name('rotateZ', driver=True), 'Rotation.Z')
        self.assertEqual(channel_name('jawSide', driver=True), 'jawSide')

    def test_quaternion_sign_only_flips_negative_w(self):
        from adv_py.core.unreal_face_solver import positive_quaternion
        self.assertEqual(positive_quaternion((.2, -.3, .4, -.5)), (-.2, .3, -.4, .5))
        self.assertEqual(positive_quaternion((.2, -.3, .4, 0.)), (.2, -.3, .4, 0.))

    def test_face_control_mapping_keeps_native_jaw_adapter(self):
        from adv_py.core.unreal_face_solver import face_control_kind, face_control_adapter
        self.assertEqual(face_control_kind('SmilePull_R'), 'driverAlias')
        self.assertEqual(face_control_kind('JawPull_M'), 'driverAdapter')
        self.assertEqual(face_control_kind('upperLid_L'), 'sampledDriver')
        self.assertEqual(face_control_kind('EyeBrowMid1_R'), 'directTransform')
        self.assertEqual(face_control_kind('unrecognized'), 'unmapped')
        mappings = face_control_adapter('JawPull_M')['mappings']
        self.assertEqual([row['operation'] for row in mappings], ['clampMax', 'clampMin', 'reuseDriver'])
        self.assertEqual(mappings[-1]['scale'], 10.)

    def test_inherited_face_translation_is_suppressed_by_local_parent(self):
        from adv_py.core.unreal_face_solver import JointSolverSample, driven_channels
        base = {name: JointSolverSample((0., 0., 0.), (1., 1., 1.), (0., 0., 0.)) for name in ('parent', 'child')}
        sample = dict(parent=replace(base['parent'], translate=(1., 0., 0.), world_position=(1., 0., 0.)),
                      child=replace(base['child'], world_position=(1., 0., 0.)))
        channels = driven_channels(('parent', 'child'), {'child': 'parent'}, base, [sample], [1.])
        self.assertEqual([(row['bone'], row['channel'], row['space']) for row in channels],
                         [('parent', 'Translation.X', 'World')])

    def test_local_child_translation_overrides_inherited_world_delta(self):
        from adv_py.core.unreal_face_solver import JointSolverSample, driven_channels
        zero = JointSolverSample((0., 0., 0.), (1., 1., 1.), (0., 0., 0.))
        sample = dict(parent=replace(zero, translate=(2., 0., 0.), world_position=(2., 0., 0.)),
                      child=replace(zero, translate=(3., 0., 0.), world_position=(5., 0., 0.)))
        channels = driven_channels(('child', 'parent'), {'child': 'parent'},
                                   dict(child=zero, parent=zero), [sample], [10.])
        self.assertEqual(channels[0]['space'], 'Local')
        self.assertEqual(channels[0]['keys'], [dict(x=10., y=3.)])

    def test_face_quaternion_and_scale_channels_keep_additive_schema(self):
        from adv_py.core.unreal_face_solver import JointSolverSample, driven_channels
        base = JointSolverSample((0., 0., 0.), (1., 1., 1.), (0., 0., 0.))
        sample = replace(base, scale=(1., 2., 1.), quaternion=(.5, 0., 0., .866))
        channels = driven_channels(('joint',), {}, {'joint': base}, [{'joint': sample}], [2.])
        self.assertEqual([row['channel'] for row in channels], ['Rotation', 'Scale.Y'])
        self.assertEqual(channels[0]['composition'], 'restThenDelta')
        self.assertEqual(channels[0]['keys'][0]['value'], [.5, 0., 0., .866])
        self.assertEqual(channels[1]['keys'], [dict(x=2., y=1.)])
        self.assertTrue(all(row['mode'] == 'Additive' and row['space'] == 'Local' for row in channels))

    def test_face_delta_threshold_does_not_emit_equal_boundary(self):
        from adv_py.core.unreal_face_solver import JointSolverSample, driven_channels
        base = JointSolverSample((0., 0., 0.), (1., 1., 1.), (0., 0., 0.))
        sample = replace(base, translate=(.0001, 0., 0.), world_position=(.0001, 0., 0.))
        self.assertEqual(driven_channels(('joint',), {}, {'joint': base}, [{'joint': sample}], [1.]), [])

    def test_body_rig_axis_ties_and_signed_secondary_follow_source(self):
        from adv_py.core.original_body_rig import dominant_axis, ik_axes
        self.assertEqual(dominant_axis((-2., 2., 2.)), ([-1., 0., 0.], 0))
        self.assertEqual(dominant_axis((1., -3., 3.)), ([0., -1., 0.], 1))
        self.assertEqual(ik_axes((5., 0., 0.), (9., 2., 2.)), ([1., 0., 0.], [0., -1., 0.]))
        self.assertEqual(ik_axes((0., 0., -5.)), ([0., 0., -1.], [0., -1., 0.]))

    def test_body_rig_sdk_uses_first_positive_key_and_zero_baseline(self):
        from adv_py.core.original_body_rig import sdk_relationship
        self.assertEqual(sdk_relationship('FKElbow_R', 'rotateZ', [-10., 0., 2., 10.], [-7., 3., 7., 40.]),
            dict(target='FKElbow_R', attribute='rotateZ', multiplier=2., driverValue=2., drivenValue=4.))

    def test_body_rig_sdk_negative_fallback_and_strict_threshold(self):
        from adv_py.core.original_body_rig import sdk_relationship
        row = sdk_relationship('FK', 'rz', [-2., 0.], [-5., 1.])
        self.assertEqual((row['driverValue'], row['multiplier']), (-2., 3.))
        self.assertIsNone(sdk_relationship('FK', 'rz', [0., .0001], [0., 1.]))
        self.assertIsNone(sdk_relationship('FK', 'rz', [0.], []))

    def test_body_rig_attribute_strings_keep_scalar_schema(self):
        from adv_py.core.original_body_rig import attribute_text
        self.assertEqual(attribute_text(True), '1')
        self.assertEqual(attribute_text(3), '3')
        self.assertEqual(attribute_text(1.25), '1.25')
        self.assertEqual(attribute_text('Main.version'), 'Main.version')
        with self.assertRaises(ValueError):
            attribute_text([1., 2., 3.])

    def test_roblox_frames_follow_authored_channel_order_and_last_zero_key(self):
        from adv_py.core.original_roblox_export import plan_roblox_head_export
        plan = plan_roblox_head_export(('JawDrop', 'EyesLookDown'))
        self.assertEqual([(frame.attribute, frame.label) for frame in plan.frames],
                         [('Frame0', 'Neutral'), ('Frame1', 'JawDrop'), ('Frame2', 'EyesLookDown')])
        self.assertEqual([(key.channel, key.frame, key.value) for key in plan.keys],
            [('JawDrop', 0, 0), ('JawDrop', 1, 10), ('JawDrop', 2, 0),
             ('EyesLookDown', 1, 0), ('EyesLookDown', 2, 10), ('EyesLookDown', 3, 0)])
        self.assertEqual((plan.playback_end, plan.current_frame), (2, 39))

    def test_roblox_empty_scalar_catalogue_keeps_neutral_frame(self):
        from adv_py.core.original_roblox_export import plan_roblox_head_export
        plan = plan_roblox_head_export(())
        self.assertEqual(plan.keys, ())
        self.assertEqual(plan.playback_end, 0)
        self.assertEqual(plan.frames[0].label, 'Neutral')

    def test_body_rig_role_boundary_maps_addresses_without_rewriting_values(self):
        from adv_py.adapters.maya_original_body_rig_roles import BodyRigRoleCommands
        class Commands:
            def __init__(self): self.calls = []
            def objExists(self, node): return node == 'AdvPy_ElbowFK_R'
            def setAttr(self, *args, **kwargs): self.calls.append((args, kwargs))
            def attributeQuery(self, *args, **kwargs): self.calls.append((args, kwargs))
            def listConnections(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return ['SDKAdvPy_ElbowFK_R.rotateZ']
        raw = Commands()
        c = BodyRigRoleCommands(raw, {'AdvPy_ElbowFK_R': 'FKElbow_R'})
        c.setAttr('FKElbow_R.label', 'FKElbow_R', type='string')
        self.assertEqual(raw.calls[-1], (('AdvPy_ElbowFK_R.label', 'FKElbow_R'), {'type': 'string'}))
        c.attributeQuery('label', node='FKElbow_R', exists=True)
        self.assertEqual(raw.calls[-1], (('label',), {'node': 'AdvPy_ElbowFK_R', 'exists': True}))
        self.assertEqual(c.listConnections('bwFKElbow_R_rotateZ.output', plugs=True), ['SDKFKElbow_R.rotateZ'])
        self.assertEqual(raw.calls[-1][0], ('bwAdvPy_ElbowFK_R_rotateZ.output',))

    def test_body_rig_role_boundary_preserves_native_name_precedence(self):
        from adv_py.adapters.maya_original_body_rig_roles import BodyRigRoleCommands
        class Commands:
            def objExists(self, node): return node == 'Main'
        c = BodyRigRoleCommands(Commands(), {'AdvPy_Global': 'Main'})
        self.assertEqual(c._map('Main.version'), 'Main.version')
        self.assertEqual(c._map('|Group|AdvPy_Global', reverse=True), '|Group|Main')

    def test_body_rig_role_boundary_rejects_ambiguous_controls(self):
        from adv_py.adapters.maya_original_body_rig_roles import BodyRigRoleCommands
        with self.assertRaises(ValueError):
            BodyRigRoleCommands(object(), {'control_a': 'Main', 'control_b': 'Main'})

    def test_fbx_namespace_callback_accepts_only_declared_native_command(self):
        from adv_py.adapters.maya_unreal_mannequin_export import _namespace_callback
        self.assertEqual(_namespace_callback('asFbxExportNameSpaceSelected "rig:export";'), 'rig:export')
        self.assertEqual(_namespace_callback('asFbxExportNameSpaceSelected ":"'), ':')
        self.assertIsNone(_namespace_callback(''))
        for text in ('delete Main;', 'asFbxExportNameSpaceSelected rig; delete Main;',
                     'asFbxExportNameSpaceSelected rig::export'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                _namespace_callback(text)

    def test_fbx_connection_identity_survives_node_rename(self):
        from adv_py.adapters.maya_unreal_mannequin_export import _plug_identity, _resolve_plug_identity
        class Commands:
            def ls(self, name, **kwargs):
                return ['uuid-1'] if kwargs.get('uuid') and name == '|Geometry|mesh' else ['|export:Geometry|export:mesh']
        c = Commands()
        identity = _plug_identity(c, '|Geometry|mesh.overrideVisibility')
        self.assertEqual(identity, ('uuid-1', 'overrideVisibility'))
        self.assertEqual(_resolve_plug_identity(c, identity), '|export:Geometry|export:mesh.overrideVisibility')

    def retired_input_record(self):
        root = OriginalGameEngineTests.state(self, '|D|Root_M', uuid='root')
        export = replace(OriginalGameEngineTests.state(self, '|D|UnrealRoot', uuid='export'),
            scale_sources=(root.path + '.scaleX', None, None))
        before = (export, root)
        plan = plan_body_game_scaling(before, enable=True)
        return mark_retired(encode(before, plan), (root.path,)), before, plan

    def test_retired_input_record_preserves_native_basis_and_orphan_nodes(self):
        from adv_py.core.original_game_scaling_record import freeze_retired_inputs, frozen_inputs, live_node_plan
        text, before, original = self.retired_input_record()
        target = 'GameEngineScalingSSCMPD2UnrealRoot.input1X'
        updated = freeze_retired_inputs(text, ((target, 2.5),))
        current, plan = decode(updated)
        self.assertEqual(current, before)
        self.assertEqual(plan.nodes, original.nodes)
        self.assertEqual(frozen_inputs(updated), ((target, 2.5),))
        replay = live_node_plan(plan, frozen_inputs(updated))
        spec = next(node for node in replay.nodes if node.name == target.split('.')[0])
        self.assertEqual(spec.input1_sources, (None, None, None))
        self.assertEqual(len(replay.nodes), len(original.nodes))

    def test_retired_input_record_rejects_an_override_of_a_live_driver(self):
        from adv_py.core.original_game_scaling_record import freeze_retired_inputs
        text, _, _ = self.retired_input_record()
        with self.assertRaises(CharacterRegistryError):
            freeze_retired_inputs(text, (('GameEngineScalingSSCMPD2Root_M.input1X', 9.),))

    def test_retired_input_cache_rejects_nonfinite_or_boolean_values(self):
        from adv_py.core.original_game_scaling_record import freeze_retired_inputs
        text, _, _ = self.retired_input_record()
        for value in (float('inf'), float('nan'), True):
            with self.subTest(value=value), self.assertRaises((CharacterRegistryError, ValueError)):
                freeze_retired_inputs(text, (('GameEngineScalingSSCMPD2UnrealRoot.input1X', value),))

    def test_retired_input_addresses_survive_namespace_roundtrip(self):
        from adv_py.core.original_game_scaling_record import freeze_retired_inputs, frozen_inputs
        text, _, _ = self.retired_input_record()
        target = 'GameEngineScalingSSCMPD2UnrealRoot.input1X'
        text = freeze_retired_inputs(text, ((target, -2.),))
        identity = CharacterIdentity('replacement')
        scoped = remap_record(text, identity.to_scene)
        self.assertEqual(frozen_inputs(scoped), ((identity.to_scene(target), -2.),))
        self.assertEqual(remap_record(scoped, identity.to_local), text)

    def test_legacy_record_does_not_invent_a_cached_input(self):
        from adv_py.core.original_game_scaling_record import frozen_inputs
        text, _, _ = self.retired_input_record()
        self.assertEqual(frozen_inputs(text), ())

    def test_frozen_input_is_not_lost_when_replacing_live_joint_uuids(self):
        from adv_py.core.original_game_scaling_record import freeze_retired_inputs, frozen_inputs
        text, before, _ = self.retired_input_record()
        values = (('GameEngineScalingSSCMPD2UnrealRoot.input1X', 3.),)
        text = freeze_retired_inputs(text, values)
        updated = replace_joint_uuids(text, {before[0].path: 'new-export'})
        self.assertEqual(frozen_inputs(updated), values)
        self.assertEqual(decode(updated)[0][0].uuid, 'new-export')
        self.assertEqual(decode(updated)[0][1].uuid, 'root')

    def test_node_audit_checks_disconnected_input_value(self):
        from adv_py.core.original_game_scaling_record import freeze_retired_inputs, frozen_inputs, live_node_plan
        from adv_py.core.body_game_scaling import GameScalingNodeState, audit_body_game_scaling_nodes
        text, _, _ = self.retired_input_record()
        target = 'GameEngineScalingSSCMPD2UnrealRoot.input1X'
        text = freeze_retired_inputs(text, ((target, 2.),))
        inputs = frozen_inputs(text)
        plan = live_node_plan(decode(text)[1], inputs)
        nodes = tuple(GameScalingNodeState(spec.name, 'multiplyDivide', spec.operation,
            spec.input1_sources, spec.input2_sources,
            (2., 0., 0.) if spec.name == target.split('.')[0] else (0., 0., 0.)) for spec in plan.nodes)
        self.assertEqual(audit_body_game_scaling_nodes(plan, nodes, frozen_inputs=inputs), ())
        wrong = tuple(replace(node, input1_value=(1., 0., 0.))
                      if node.name == target.split('.')[0] else node for node in nodes)
        self.assertTrue(audit_body_game_scaling_nodes(plan, wrong, frozen_inputs=inputs))

    def test_fbx_history_path_uses_last_extension_and_nearest_quote(self):
        from adv_py.core.original_fbx_export import source_fbx_path_from_line
        self.assertEqual(source_fbx_path_from_line('export "C:/old.fbx" to "D:/my models/hero.FBX";'),
                         'D:/my models/hero.FBX')
        self.assertEqual(source_fbx_path_from_line('Exported C:\\my models\\hero.fbx successfully'),
                         'C:\\my models\\hero.fbx')
        self.assertEqual(source_fbx_path_from_line('path: /tmp/hero.fbx done'), '/tmp/hero.fbx')
        self.assertEqual(source_fbx_path_from_line('hero.fbx.backup'), 'hero.fbx')

    def test_fbx_history_keeps_the_source_final_line_overwrite(self):
        from adv_py.core.original_fbx_export import source_fbx_path_from_history
        self.assertEqual(source_fbx_path_from_history('Exported "C:/hero.fbx"\n'), 'C:/hero.fbx')
        self.assertEqual(source_fbx_path_from_history('Exported "C:/hero.fbx"\nFinished\n'), '')

    def test_native_skin_chain_reverses_deformation_chain_and_removes_duplicates(self):
        from adv_py.adapters.maya_original_skin_history import native_skin_cluster_chain
        class Commands:
            def deformableShape(self, node, **flags):
                return ['upstream', 'skinA', 'skinB', 'skinA']
            def ls(self, nodes, **flags):
                return [node for node in nodes if node.startswith('skin')]
        self.assertEqual(native_skin_cluster_chain(Commands(), 'mesh'), ('skinA', 'skinB'))

    def test_native_remove_unused_uses_first_skin_per_selected_object(self):
        from adv_py.adapters.maya_original_skin_history import remove_unused_selected_skin_influences
        class Commands:
            def __init__(self): self.edited = []; self.updated = False
            def ls(self, nodes=None, **flags):
                return ['skinA', 'skinB'] if nodes is not None else ['mesh']
            def deformableShape(self, node, **flags): return ['skinA', 'skinB']
            def skinCluster(self, skin, **flags):
                if flags.get('query'): return 2
                self.edited.append(skin)
            def select(self, *args, **flags): self.updated = True
        c = Commands()
        self.assertEqual(remove_unused_selected_skin_influences(c), 2)
        self.assertEqual(c.edited, ['skinB'])
        self.assertTrue(c.updated)

    def test_mannequin_blend_shape_copy_does_not_write_a_reconnected_source(self):
        from adv_py.adapters.maya_unreal_mannequin import MayaMannequinHost
        class Commands:
            def __init__(self):
                self.edges = {'asFaceBS.Smile': 'driver.output'}
                self.source_values = []; self.deleted = []; self.alias_writes = []
            def listHistory(self, *args, **flags): return ['asFaceBS']
            def nodeType(self, node): return 'blendShape'
            def listAttr(self, *args, **flags): return ['Smile']
            def select(self, *args, **flags): pass
            def blendShape(self, *args, **flags): return ['uemasFaceBS']
            def listConnections(self, plug, **flags): return [self.edges[plug]] if plug in self.edges else []
            def disconnectAttr(self, source, target): del self.edges[target]
            def connectAttr(self, source, target): self.edges[target] = source
            def setAttr(self, plug, value):
                if plug in self.edges: raise RuntimeError('cannot write a connected plug')
                self.source_values.append(value)
            def duplicate(self, *args, **flags): return ['Smile']
            def aliasAttr(self, *args, **flags):
                if flags.get('query'): return 'Smile'
                self.alias_writes.append(args)
            def delete(self, node): self.deleted.append(node)
            def isConnected(self, source, target): return self.edges.get(target) == source
            def objExists(self, node): return True
        c = Commands()
        host = object.__new__(MayaMannequinHost)
        host._cmds = c
        host._copy_face_blend_shapes('sourceMesh', 'targetMesh', 'sourceSkin')
        self.assertEqual(c.source_values, [1, 0])
        self.assertEqual(c.edges['asFaceBS.Smile'], 'driver.output')
        self.assertEqual(c.edges['uemasFaceBS.weight[0]'], 'driver.output')
        self.assertEqual(c.alias_writes, [])
        self.assertEqual(c.deleted, ['Smile'])


class OriginalFaceReductionPolicyTests(unittest.TestCase):
    def test_custom_reduce_stops_at_first_gap_and_keeps_boundary_and_unrelated_joints(self):
        from adv_py.core.original_face_reduction import custom_face_reduction
        joints = ('FaceJoint_M', 'EyeLidJoints_M', 'upperLidBase_R',
                  'upperLidMain0_R', 'upperLidMain1_R', 'upperLidMain2_R',
                  'upperLidMain4_R', 'upperLidOuter1_R', 'Jaw_M')
        plan = custom_face_reduction('EyeLid', 2, joints, set(joints).__contains__, 17)
        self.assertEqual(plan.reported_count, 8)
        self.assertEqual(plan.removed, ('upperLidMain1_R', 'upperLidOuter1_R'))
        self.assertEqual(plan.kept, ('upperLidMain0_R', 'upperLidMain2_R', 'upperLidMain4_R'))

    def test_lip_anchor_overlaps_preserve_three_independent_source_assignments(self):
        from adv_py.core.original_face_reduction import original_lip_anchor_indices, original_lip_anchor_letter
        indices = original_lip_anchor_indices(((0., 0., 0.), (2., 0., 0.)),
                                              ((1., 0., 0.),) * 3)
        self.assertEqual(indices, (0, 0, 0))
        self.assertEqual(original_lip_anchor_letter(0, indices), 'C')
        self.assertIsNone(original_lip_anchor_letter(1, indices))

    def test_lid_anchor_excludes_endpoints_and_preserves_999_fallback(self):
        from adv_py.core.original_face_reduction import original_lid_anchor_indices
        positions = ((0., 0., 0.), (5., 0., 0.), (10., 0., 0.))
        self.assertEqual(original_lid_anchor_indices(positions, ((0., 0., 0.),) * 3), (1, 1, 1))
        self.assertEqual(original_lid_anchor_indices(positions, ((2000., 0., 0.),) * 3,
                                                    previous=(3, 4, 5)), (3, 4, 5))

    def test_nearest_pair_uses_two_passes_and_native_weight_ratio(self):
        from adv_py.core.original_face_reduction import original_lid_nearest_pair
        self.assertEqual(original_lid_nearest_pair((1., 0., 0.),
            ((0., 0., 0.), (4., 0., 0.), (20., 0., 0.))), (0, 1, .75))

    def test_second_largest_threshold_is_not_an_invented_normalization(self):
        from adv_py.core.original_face_reduction import reduction_balance_threshold
        self.assertIsNone(reduction_balance_threshold((.7,)))
        self.assertEqual(reduction_balance_threshold((.05, .6, .2, .15)), .2)

    def test_preview_and_apply_share_one_transaction_without_face_build(self):
        from contextlib import contextmanager
        from adv_py.application.original_face_reduction import CustomReduceOriginalFace
        class Host:
            def __init__(self): self.calls = []
            def capture_original_custom_face_reduction(self, kind, every):
                self.calls.append(('capture', kind, every)); return 'captured'
            @contextmanager
            def transaction(self, name):
                self.calls.append('open'); yield; self.calls.append('close')
            def apply_original_custom_face_reduction(self, plan, *, preview):
                self.calls.append((plan, preview)); return 'result'
        host = Host()
        self.assertEqual(CustomReduceOriginalFace(host).apply('Lip', 3, preview=True), 'result')
        self.assertEqual(host.calls, [('capture', 'Lip', 3), 'open', ('captured', True), 'close'])


class OriginalOptimizeAndSkinPolicyTests(unittest.TestCase):
    def test_unused_attribute_native_typo_locked_and_connected_guards(self):
        from adv_py.core.original_optimize import removable_original_control_attribute
        self.assertFalse(removable_original_control_attribute('curveUnafeccted', locked=False, connected=False))
        self.assertFalse(removable_original_control_attribute('custom', locked=True, connected=False))
        self.assertFalse(removable_original_control_attribute('custom', locked=False, connected=True))
        self.assertTrue(removable_original_control_attribute('custom', locked=False, connected=False))

    def test_ui_cleanup_flushes_only_after_its_chunk_is_closed(self):
        from contextlib import contextmanager
        from adv_py.application.original_optimize import OptimizeOriginalRig
        class Host:
            def __init__(self): self.calls = []
            def preflight_original_optimize(self, operation): self.calls.append('capture')
            @contextmanager
            def transaction(self, name):
                self.calls.append('open'); yield; self.calls.append('close')
            def delete_saved_original_uis(self): self.calls.append('delete'); return ('ui',)
            def flush_original_saved_ui_undo(self): self.calls.append('flush')
        host = Host()
        self.assertEqual(OptimizeOriginalRig(host).apply('delete_saved_uis'), ('ui',))
        self.assertEqual(host.calls, ['capture', 'open', 'delete', 'close', 'flush'])

    def test_bind_matrix_freeze_preserves_sparse_logical_indices_without_mel(self):
        from adv_py.adapters.maya_deform_skinning import freeze_native_skin_cluster
        matrix = tuple(float(value) for value in range(16))
        class Commands:
            def __init__(self): self.writes = []; self.reads = []
            def objExists(self, node): return node == 'skin'
            def listConnections(self, plug, **flags):
                return ['skin.matrix[2]', '|Rig|A.worldMatrix[0]',
                        'skin.matrix[19]', 'Other:B.worldMatrix[0]']
            def getAttr(self, plug): self.reads.append(plug); return [matrix]
            def setAttr(self, plug, *values, **flags): self.writes.append((plug, values, flags))
        c = Commands()
        freeze_native_skin_cluster('missing', cmds=c)
        self.assertEqual(c.writes, [])
        freeze_native_skin_cluster('skin', cmds=c)
        self.assertEqual(c.reads, ['|Rig|A.worldInverseMatrix', 'Other:B.worldInverseMatrix'])
        self.assertEqual(c.writes, [('skin.bindPreMatrix[2]', matrix, {'type': 'matrix'}),
                                  ('skin.bindPreMatrix[19]', matrix, {'type': 'matrix'})])


class OriginalPublishPolicyTests(unittest.TestCase):
    def test_native_publish_paths_defaults_and_custom_order(self):
        from adv_py.core.original_publish import original_publish_entries, plan_original_publish
        entries = original_publish_entries(('LoOnly=delete Hi;', 'Default=first;',
                                             'BodyOnly=body;', 'Default=last;'))
        plan = plan_original_publish('D:/scenes/hero.mb', entries)
        self.assertEqual(plan.destination.replace('\\', '/'), 'D:/scenes/hero_Published.mb')
        self.assertEqual(tuple(entry.name for entry, _ in plan.variants), ('LoOnly', 'BodyOnly'))
        self.assertEqual(plan.default_script, 'last;')
        self.assertEqual(plan_original_publish('hero.ma').destination, 'hero.mb')
        self.assertEqual(plan_original_publish('hero.MB').destination, 'hero.mb')

    def test_native_option_strings_keep_script_equals_and_slot_order(self):
        from adv_py.core.original_publish import original_publish_entries, replace_original_publish_entry
        values = ('A=x=2;\ny=3;', 'B=old;', 'C=third;')
        self.assertEqual(original_publish_entries(values)[0].script, 'x=2;\ny=3;')
        self.assertEqual(replace_original_publish_entry(values, 'B', 'new=4;'),
                         ('A=x=2;\ny=3;', 'B=new=4;', 'C=third;'))
        self.assertEqual(replace_original_publish_entry(values, 'D', ''), (*values, 'D='))

    def test_unsaved_scene_rejected_before_publish(self):
        from adv_py.core.original_publish import plan_original_publish
        with self.assertRaises(ValueError): plan_original_publish('')

    def test_binary_export_failure_still_restores_the_script_chunk(self):
        from adv_py.adapters.maya_original_publish import MayaOriginalPublishHost
        class Commands:
            def __init__(self): self.calls = []
            def undoInfo(self, **flags): self.calls.append(flags)
            def file(self, *args, **flags): raise RuntimeError('export failed')
            def undo(self): self.calls.append('undo')
        host = object.__new__(MayaOriginalPublishHost)
        host._cmds = Commands()
        host._publish_run_script = lambda script: None
        with self.assertRaisesRegex(RuntimeError, 'export failed'):
            host._publish_variant('script', 'target.mb', 'BodyOnly', custom=True)
        self.assertEqual(host._cmds.calls, [
            {'openChunk': True, 'chunkName': 'PublishScript for: "BodyOnly"'},
            {'closeChunk': True}, {'stateWithoutFlush': False},
            {'stateWithoutFlush': True}, 'undo'])


if __name__ == '__main__':
    unittest.main()
