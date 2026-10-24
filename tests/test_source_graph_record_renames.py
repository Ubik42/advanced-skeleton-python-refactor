"""Native converter renames must preserve the closed registration graph."""
from dataclasses import replace
import unittest

from adv_py.adapters.maya_source_graph_records import rename_addresses
from adv_py.core.character_registry import (
    REGISTRY_NAME, decode_registration, encode_registration,
)
from test_character_registry import registration_fixture


class RecordCommands:
    def __init__(self, registration):
        self.document = REGISTRY_NAME + '.advPyRegistryDocument'
        self.values = {self.document: encode_registration(registration)}
        self.locked = {self.document: True}

    def ls(self, **kwargs):
        return tuple(dict.fromkeys(plug.split('.', 1)[0] for plug in self.values))

    def objExists(self, plug):
        return plug in self.values

    def getAttr(self, plug, **kwargs):
        if kwargs.get('type'):
            return 'bool' if isinstance(self.values[plug], bool) else 'string'
        if kwargs.get('lock'):
            return self.locked[plug]
        return self.values[plug]

    def setAttr(self, plug, value=None, **kwargs):
        if 'lock' in kwargs:
            self.locked[plug] = kwargs['lock']
        else:
            if self.locked[plug]:
                raise AssertionError('Attempted write to locked registration')
            self.values[plug] = value


class RecordHost:
    namespace = None

    def __init__(self, registration):
        self._cmds = RecordCommands(registration)
        self._transaction_changed = False

    def _require_transaction(self):
        pass

    def scene_address(self, address):
        return address


class SourceGraphRecordRenameTests(unittest.TestCase):
    def test_opm_boolean_markers_are_not_json_graph_records(self):
        host = RecordHost(registration_fixture())
        for attribute in ('advPySourceBodyMatrix', 'advPySourceLegLockMatrix'):
            plug = '|LegLock.' + attribute
            host._cmds.values[plug] = True
            host._cmds.locked[plug] = True
        before = dict(host._cmds.values)
        rename_addresses(host, {'OldReverse': 'FKIKBlendLeg_LReverse'})
        self.assertEqual(host._cmds.values, before)
        self.assertTrue(all(host._cmds.locked.values()))

    def test_rebuild_policy_removes_only_registered_nested_sdk_layers(self):
        from adv_py.adapters.maya_source_body_rebuild import _pre_aim_controls
        ancestor = '|Controls|SDKCup'
        nested = ancestor + '|CupExtra|Cup|FingerOffset|SDKFinger'
        control = nested + '|FingerExtra|Finger'
        expected = '|Controls|CupExtra|Cup|FingerOffset|FingerExtra|Finger'
        authored = '|Controls|SDKAuthored|UnrelatedFK'
        self.assertEqual(_pre_aim_controls((control, authored), {ancestor, nested}),
                         frozenset((expected, authored)))

    def test_converter_rename_preserves_identities_and_unrelated_input(self):
        before = registration_fixture()
        selected = before.nodes[0]
        selected = replace(selected, inputs=(
            ('rotateY', 'unitConversion1.output'),
            ('rotateZ', 'unitConversion10.output')))
        before = replace(before, nodes=(selected,) + before.nodes[1:])
        host = RecordHost(before)
        rename_addresses(host, {'unitConversion1': 'bwSDKFinger_rotateY_outputUC'})
        after = decode_registration(host._cmds.values[host._cmds.document])
        self.assertEqual(after.nodes[0].inputs, (
            ('rotateY', 'bwSDKFinger_rotateY_outputUC.output'),
            ('rotateZ', 'unitConversion10.output')))
        self.assertEqual(replace(after, nodes=before.nodes), before)
        self.assertEqual(tuple((n.path, n.uuid, n.parent) for n in after.nodes),
                         tuple((n.path, n.uuid, n.parent) for n in before.nodes))
        self.assertTrue(host._cmds.locked[host._cmds.document])
        self.assertTrue(host._transaction_changed)


if __name__ == '__main__':
    unittest.main()
