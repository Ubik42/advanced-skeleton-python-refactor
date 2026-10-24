from dataclasses import dataclass, replace
from types import SimpleNamespace as Row
import unittest
from unittest.mock import patch

from adv_py.adapters.maya_character_properties import plan, connection_plugs
from adv_py.adapters.maya_driving_rebuild import derived_property_plugs, DrivingRebuildState, restore_membership, _owned_sdk_nodes
from adv_py.adapters.maya_driving_rebuild_graph import DrivingGraphState, DrivingGraphNode
from adv_py.core.character_preservation import PreservedExtension
from adv_py.core.character_registry import CharacterRegistryError


class DrivingRebuildPropertyTests(unittest.TestCase):
    def test_authored_sdk_limits_keep_portable_contract_only_when_native_copy_matches(self):
        from adv_py.adapters.maya_driving_registration import preserve_driver_channel_contract
        from adv_py.core.character_registry import CharacterChannel
        original_channel = CharacterChannel('driving.Fingers_L.cup', '|DrivingSystem|Fingers_L', 'cup', None, None)
        rebuilt_channel = replace(original_channel, minimum=-15., maximum=20.)
        queries = {'minimum': -15., 'maximum': 20., 'softMin': -12., 'softMax': 18.}
        def host(limits):
            def query(attribute, node, **flags):
                flag = next(iter(flags))
                return True if flag.endswith('Exists') else [limits[flag]]
            return Row(scene_address=lambda value: value, _cmds=Row(
                ls=lambda value, **flags: [value if value.startswith('|') else '|' + value], sets=lambda *args, **flags: True,
                attributeQuery=query, getAttr=lambda *args, **flags: 'double'))
        @dataclass(frozen=True)
        class Registration:
            channels: tuple
        original = Registration((original_channel,))
        replacement = Registration((rebuilt_channel,))
        result = preserve_driver_channel_contract(host(queries), host(queries), original, replacement)
        self.assertEqual(result.channels, original.channels)
        with self.assertRaises(CharacterRegistryError):
            preserve_driver_channel_contract(host(queries), host(dict(queries, softMax=17.)), original, replacement)

    def test_existing_definition_row_verifies_its_declared_connections(self):
        row = PreservedExtension('|ArmSettings', 'id', 'transform', None, None, (), (
            ('UnitConversion.output', '|ArmSettings.armIkFk_L'),
            ('|ArmSettings.armIkFk_L', 'ParentBlend.target[0].weight'),
            ('|ArmSettings.armIkFk_R', 'UserMonitor.input')))
        self.assertEqual(connection_plugs(row), frozenset((
            '|ArmSettings.armIkFk_L', '|ArmSettings.armIkFk_R')))

    def test_rebuild_uses_live_driver_curves_and_native_fit_order(self):
        from adv_py.adapters.maya_driving_rebuild import _capture_live_fit_systems
        from adv_py.adapters.maya_body_driving_fit import (
            DrivingFitPlan, DrivingFitControl, DrivingFitAttribute)
        fit = '|FitSkeleton'
        curve = 'SDKFKCup_L_rotateX1'
        control = DrivingFitControl('|Group|DrivingSystem|Fingers_L',
            'drivingSystem_Fingers_L', (
                DrivingFitAttribute('cup', (curve,), -10., 10., -5., 5.),))
        host = Row(plan_body_driving_fit_sync=lambda target: DrivingFitPlan(target, (control,)),
                   _cmds=Row(ls=lambda name, **flags: ['live-curve-uuid'],
                             objExists=lambda name: True,
                             listConnections=lambda *args, **flags: ['|FitSkeleton.drivingSystem[21]']))
        driving = Row(capture_original_driving_fit_restore=lambda target: self.fail('stale Fit arrays'))
        systems = _capture_live_fit_systems(host, driving, fit)
        self.assertEqual(systems[0].control, 'Fingers_L')
        self.assertEqual(systems[0].nesting_depth, 3)
        row = systems[0].curves[0]
        self.assertEqual((row.driven, row.driven_attribute), ('FKCup_L', 'rotateX'))
        self.assertEqual(row.limits, (-10., 10., -5., 5.))
        self.assertEqual(row.source_uuid, 'live-curve-uuid')
        self.assertEqual(row.fit_index, 0)
        self.assertEqual(row.message_index, 21)

    def test_absent_live_driving_system_retains_fit_source_capture(self):
        from adv_py.adapters.maya_driving_rebuild import _capture_live_fit_systems
        host = Row(plan_body_driving_fit_sync=lambda fit: None)
        driving = Row(capture_original_driving_fit_restore=lambda fit: ('template-system',))
        self.assertEqual(_capture_live_fit_systems(host, driving, 'FitSkeleton'), ('template-system',))

    def test_sdk_ownership_reads_live_receiver_and_excludes_fit_templates(self):
        sdk = '|Controls|SDKHand'
        sources = {sdk+'.rotateX': ['OutputUC.output'],
                   'OutputUC.input': ['Weighted.output'],
                   'Weighted.input': ['LiveCurve.output', 'FitTemplate.output']}
        kinds = {'OutputUC': 'unitConversion', 'Weighted': 'blendWeighted',
                 'LiveCurve': 'animCurveUA', 'FitTemplate': 'animCurveUA'}
        commands = Row(objExists=lambda plug: plug == 'AllSet' or plug.startswith(sdk+'.advPySourceDrivingSDK'),
                       listConnections=lambda plug, **flags: sources.get(plug, []),
                       nodeType=lambda node: kinds[node],
                       sets=lambda node, **flags: node in ('OutputUC','LiveCurve'))
        host = Row(_cmds=commands)
        registration = Row(nodes=(Row(path=sdk),))
        self.assertEqual(_owned_sdk_nodes(host, registration),
                         (('LiveCurve','animCurveUA'), ('OutputUC','unitConversion')))

    def test_saved_sdk_membership_replays_only_declared_objects(self):
        state = DrivingRebuildState((), (), (), owned_sdk_nodes=(
            ('SDKCurve', 'animCurveUA'), ('SDKCurve_outputUC', 'unitConversion')))
        kinds = {'SDKCurve': 'animCurveUA', 'SDKCurve_outputUC': 'unitConversion',
                 'AuthoredCurve': 'animCurveUA'}
        written = []
        commands = Row(ls=lambda name, **flags: [name] if name in kinds else [],
                       nodeType=lambda name: kinds[name],
                       sets=lambda name, **flags: written.append((name, flags)))
        host = Row(_cmds=commands, _require_transaction=lambda: None,
                   _transaction_changed=False)
        restore_membership(host, state)
        self.assertEqual(written, [('SDKCurve', {'add': 'AllSet'}),
                                  ('SDKCurve_outputUC', {'add': 'AllSet'})])

    def test_missing_sdk_member_does_not_partially_write_membership(self):
        state = DrivingRebuildState((), (), (), owned_sdk_nodes=(
            ('SDKCurve', 'animCurveUA'), ('Missing', 'unitConversion')))
        written = []
        commands = Row(ls=lambda name, **flags: [name] if name == 'SDKCurve' else [],
                       nodeType=lambda name: 'animCurveUA',
                       sets=lambda name, **flags: written.append(name))
        host = Row(_cmds=commands, _require_transaction=lambda: None)
        with self.assertRaises(CharacterRegistryError):
            restore_membership(host, state)
        self.assertEqual(written, [])

    def definition(self, value, kind='double'):
        return ('qRotateX', kind, value, False, True,
                (('niceName', 'Q Rotate X'), ('channelBox', False), ('default', (0.,))))

    def context(self, kind='double'):
        path = '|Group|Root_M|Elbow_R'
        source = PreservedExtension(path, 'source-id', 'joint', None, None,
                                    (self.definition(35.),), ())
        target = replace(source, uuid='new-id', attributes=(self.definition(0., kind),))
        original = Row(properties=(source,), registration=Row(channels=()))
        host = Row(_cmds=Row(objExists=lambda plug: plug == path + '.qRotateX'))
        return original, host, target

    def test_captured_derived_value_is_not_written_to_new_connected_output(self):
        original, host, target = self.context()
        with patch('adv_py.adapters.maya_body.MayaBodyBuildHost', return_value=host), \
             patch('adv_py.adapters.maya_character_properties.capture_extension', return_value=target):
            self.assertEqual(plan(host, original, 'stage', derived_plugs=
                                  frozenset((target.path + '.qRotateX',))), ())
            with self.assertRaises(CharacterRegistryError):
                plan(host, original, 'stage')

    def test_derived_definition_mismatch_is_still_rejected(self):
        original, host, target = self.context('float')
        with patch('adv_py.adapters.maya_body.MayaBodyBuildHost', return_value=host), \
             patch('adv_py.adapters.maya_character_properties.capture_extension', return_value=target):
            with self.assertRaises(CharacterRegistryError):
                plan(host, original, 'stage', derived_plugs=
                     frozenset((target.path + '.qRotateX',)))

    def test_existing_derived_definition_keeps_declared_external_reader_edge(self):
        original, host, target = self.context()
        edge=(target.path+'.qRotateX','user:Monitor.input')
        original.properties=(replace(original.properties[0],connections=(edge,)),)
        with patch('adv_py.adapters.maya_body.MayaBodyBuildHost',return_value=host), \
             patch('adv_py.adapters.maya_character_properties.capture_extension',return_value=target):
            rows=plan(host,original,'stage',derived_plugs=frozenset((target.path+'.qRotateX',)))
        self.assertEqual(rows[0].attributes,())
        self.assertEqual(rows[0].connections,(edge,))

    def test_only_captured_graph_outputs_on_registered_nodes_are_derived(self):
        node = PreservedExtension('ElbowQRotateXQTETwist_R', 'q-id', 'quatToEuler',
                                 None, None, (), ())
        graph = DrivingGraphState((DrivingGraphNode(node, (), False),), (
            ('ElbowQRotateXQTETwist_R.outputRotateX', 'Elbow_R.qRotateX'),
            ('userLogic.output', 'Elbow_R.customValue'),
            ('ElbowQRotateXQTETwist_R.outputRotateX', 'foreign:Elbow_R.customValue'),))
        state = DrivingRebuildState((), (), (), graph)
        registration = Row(nodes=(Row(path='|Group|Root_M|Elbow_R'),))
        self.assertEqual(derived_property_plugs(state, registration),
                         frozenset(('|Group|Root_M|Elbow_R.qRotateX',)))
