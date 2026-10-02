from dataclasses import replace
from types import SimpleNamespace as Row
import unittest
from unittest.mock import patch

from adv_py.adapters.maya_character_properties import plan
from adv_py.adapters.maya_driving_rebuild import derived_property_plugs, DrivingRebuildState
from adv_py.adapters.maya_driving_rebuild_graph import DrivingGraphState, DrivingGraphNode
from adv_py.core.character_preservation import PreservedExtension
from adv_py.core.character_registry import CharacterRegistryError


class DrivingRebuildPropertyTests(unittest.TestCase):
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
