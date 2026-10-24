"""Source duplicate Fit naming carries the native SDK descriptor and graph."""
import unittest

from adv_py.adapters.maya_source_fit_unique_names import MayaSourceFitUniqueNamesMixin
from adv_py.core.source_fit_unique_names import (
    legacy_driving_curve_name, source_fit_driving_copy, source_fit_unique_order,
)


class Commands:
    def __init__(self):
        self.nodes = {'a': '|FitSkeleton|Hand|IndexFinger',
                      'b': '|FitSkeleton|Hand2|IndexFinger'}
        self.curves = ['SDK1IndexFingerCurl']
        self.attrs = {'DS_IndexFinger_Curl'}
        self.connections = []
        self.calls = []

    def listConnections(self, node, **options):
        if node == '|FitSkeleton':
            return self.curves[:]
        if options.get('connections'):
            return [node+'.input', '|FitSkeleton.DS_IndexFinger_Curl[0]']
        return ['|FitSkeleton.DS_IndexFinger_Curl[0]']

    def listRelatives(self, *args, **options):
        return list(self.nodes.values())

    def ls(self, name, **options):
        if name in self.nodes:
            return [self.nodes[name]]
        return [path for path in self.nodes.values()
                if path == name or path.rsplit('|', 1)[-1] == name]

    def objExists(self, node):
        return node in self.curves or bool(self.ls(node))

    def rename(self, old, new):
        self.calls.append(('rename', old, new))
        if old in self.curves:
            self.curves[self.curves.index(old)] = new
            return new
        identity = next(identity for identity, path in self.nodes.items() if path == old)
        self.nodes[identity] = old.rsplit('|', 1)[0]+'|'+new
        return self.nodes[identity]

    def duplicate(self, curve, *, name):
        self.calls.append(('duplicate', curve, name))
        return [name]

    def attributeQuery(self, attribute, **options):
        return attribute in self.attrs

    def addAttr(self, node, **options):
        self.calls.append(('addAttr', node, options))
        self.attrs.add(options['longName'])

    def getAttr(self, plug, *, size):
        return len([source for source, target in self.connections
                    if source.startswith(plug+'[')])

    def connectAttr(self, source, target):
        self.connections.append((source, target))

    def select(self, *nodes, **options):
        self.calls.append(('select', nodes))


class Host(MayaSourceFitUniqueNamesMixin):
    def __init__(self, commands):
        self._cmds = commands
        self._transaction_changed = False

    def _require_transaction(self):
        pass

    def _resolve_transform(self, *args):
        return '|FitSkeleton'

    def _fit_node_uuid(self, path):
        return next(identity for identity, candidate in self._cmds.nodes.items() if path == candidate)

    def _fit_node_from_uuid(self, identity):
        return self._cmds.nodes[identity]


class SourceFitUniqueNamesTests(unittest.TestCase):
    def test_sdk_compatibility_is_native_single_character_removal(self):
        self.assertEqual(legacy_driving_curve_name('SDK1Finger'), 'SDKFinger')
        self.assertEqual(legacy_driving_curve_name('stage:SDK12Finger'), 'stage:SDK2Finger')
        self.assertIsNone(legacy_driving_curve_name('SDKFinger'))
        self.assertIsNone(legacy_driving_curve_name('Other1Finger'))

    def test_recipe_replaces_first_name_and_uses_native_three_tokens(self):
        recipe = source_fit_driving_copy('stage:SDKHandHand', 'Hand', 'Hand2', 2,
                                        'stage:FitSkeleton.DS_Hand_Curl_extra[3]')
        self.assertEqual(recipe.target, 'stage:SDKHand2Hand')
        self.assertEqual(recipe.attribute, 'DS_Hand2_Curl')

    def test_unrelated_sdk_is_not_copied(self):
        self.assertIsNone(source_fit_driving_copy('SDKFoot', 'Hand', 'Hand2', 2, 'invalid'))

    def test_bad_driver_descriptor_rejects_missing_or_short_attribute(self):
        for plug in ('bad', 'FitSkeleton.Curl', 'FitSkeleton.DS__Curl[0]'):
            with self.assertRaises(ValueError):
                source_fit_driving_copy('SDKHand', 'Hand', 'Hand1', 1, plug)

    def test_native_hand_move_to_front_preserves_the_mutating_loop_order(self):
        joints = ('Tip', 'ThumbA', 'ThumbB', 'Pinky', 'Ring', 'Middle', 'Cup', 'Index')
        self.assertEqual(source_fit_unique_order(joints, duplicated_index_finger=True),
                         ('Index', 'Cup', 'Middle', 'Ring', 'Pinky', 'ThumbB', 'ThumbA', 'Tip'))
        self.assertEqual(source_fit_unique_order(joints, duplicated_index_finger=False), joints)

    def test_host_normalization_duplicates_sdk_and_reconnects_fit_multi(self):
        commands = Commands()
        host = Host(commands)
        host.normalize_fit_joint_names('FitSkeleton')
        self.assertEqual(set(path.rsplit('|', 1)[-1] for path in commands.nodes.values()),
                         {'IndexFinger', 'IndexFinger1'})
        self.assertIn(('duplicate', 'SDKIndexFingerCurl', 'SDKIndexFinger1Curl'), commands.calls)
        self.assertEqual(commands.connections,
                         [('|FitSkeleton.DS_IndexFinger1_Curl[0]', 'SDKIndexFinger1Curl.input')])
        self.assertTrue(host._transaction_changed)
        self.assertEqual(commands.calls[0], ('rename', 'SDK1IndexFingerCurl', 'SDKIndexFingerCurl'))

    def test_existing_duplicate_sdk_target_is_rejected_before_curve_copy(self):
        commands = Commands()
        commands.curves = ['SDKIndexFingerCurl', 'SDKIndexFinger1Curl']
        with self.assertRaises(ValueError):
            Host(commands)._source_fit_copy_driving_systems('|FitSkeleton', 'IndexFinger', 'IndexFinger1', 1)
        self.assertFalse(any(call[0] == 'duplicate' for call in commands.calls))

    def test_existing_fit_multi_attribute_is_reused_at_its_native_size(self):
        commands = Commands()
        commands.curves = ['SDKIndexFingerCurl']
        commands.attrs.add('DS_IndexFinger1_Curl')
        commands.connections = [('|FitSkeleton.DS_IndexFinger1_Curl[0]', 'Other.input')]
        Host(commands)._source_fit_copy_driving_systems('|FitSkeleton', 'IndexFinger', 'IndexFinger1', 1)
        self.assertEqual(commands.connections[-1],
                         ('|FitSkeleton.DS_IndexFinger1_Curl[1]', 'SDKIndexFinger1Curl.input'))
        self.assertFalse(any(call[0] == 'addAttr' for call in commands.calls))


if __name__ == '__main__':
    unittest.main()
