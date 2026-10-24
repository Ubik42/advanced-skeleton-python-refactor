"""Native Face settings round trips use enum indices and source defaults."""
from contextlib import contextmanager
import unittest

from adv_py.adapters.maya_original_face_options import MayaOriginalFaceOptionsMixin
from adv_py.application.original_face_options import SetOriginalFaceOptions
from adv_py.core.original_face_options import normalize_original_face_options


class OptionCommands:
    def __init__(self):
        self.types = {}
        self.values = {}
        self.enums = {}
        self.calls = []

    def objExists(self, plug):
        return plug in self.types

    def referenceQuery(self, *args, **flags):
        return False

    def getAttr(self, plug, **flags):
        if flags.get('type'):
            return self.types[plug]
        if flags.get('asString'):
            return self.enums[plug][self.values[plug]]
        return self.values[plug]

    def addAttr(self, node, **flags):
        plug = node+'.'+flags['longName']
        self.types[plug] = flags.get('attributeType', flags.get('dataType'))
        self.values[plug] = 0
        if flags.get('enumName'):
            self.enums[plug] = tuple(flags['enumName'].rstrip(':').split(':'))
        self.calls.append(('add', plug))

    def setAttr(self, plug, value, **flags):
        if self.types[plug] == 'enum' and not 0 <= value < len(self.enums[plug]):
            raise RuntimeError('Old enum rejects added index')
        self.values[plug] = value
        self.calls.append(('set', plug, value))

    def deleteAttr(self, plug):
        self.types.pop(plug)
        self.values.pop(plug)
        self.enums.pop(plug, None)
        self.calls.append(('delete', plug))


class OptionsHost(MayaOriginalFaceOptionsMixin):
    def __init__(self, *, fit=True):
        self._cmds = OptionCommands()
        self.exists = fit
        self._transaction_changed = False
        self.active = False
        self.sides = []

    def _fit(self, **flags):
        return 'FaceFitSkeleton' if self.exists else None

    def _require_transaction(self):
        if not self.active:
            raise AssertionError('Options written without transaction')

    @contextmanager
    def transaction(self, label):
        self.active = True
        try:
            yield
        finally:
            self.active = False

    def switch_original_face_fit_side(self, side):
        self.sides.append(side)


class OriginalFaceOptionsTests(unittest.TestCase):
    def test_missing_attributes_keep_native_defaults(self):
        values = OptionsHost().read_original_face_options()
        self.assertTrue(values['Phonemes'])
        self.assertTrue(values['Emotions'])
        self.assertFalse(values['NonSym'])
        self.assertEqual(values['LipCtrls'], '12')
        self.assertEqual(values['MaxInf'], '4')

    def test_enum_serialization_round_trips_menu_index_not_label_number(self):
        host = OptionsHost()
        values = SetOriginalFaceOptions(host).apply({'LipCtrls': '20', 'MaxInf': '8', 'RigType': 'Mixed'})
        self.assertEqual(host._cmds.values['FaceFitSkeleton.LipCtrls'], 2)
        self.assertEqual(host._cmds.values['FaceFitSkeleton.MaxInf'], 1)
        self.assertEqual(host._cmds.values['FaceFitSkeleton.RigType'], 2)
        self.assertEqual(values['LipCtrls'], '20')
        self.assertEqual(values['MaxInf'], '8')

    def test_old_short_enum_and_legacy_non_sym_string_follow_native_conversion(self):
        host = OptionsHost()
        c = host._cmds
        c.types.update({'FaceFitSkeleton.RigType': 'enum', 'FaceFitSkeleton.NonSym': 'string'})
        c.enums['FaceFitSkeleton.RigType'] = ('Joints', 'BlendShapes')
        c.values.update({'FaceFitSkeleton.RigType': 0, 'FaceFitSkeleton.NonSym': 'old'})
        self.assertFalse(host.read_original_face_options()['NonSym'])
        SetOriginalFaceOptions(host).apply({'RigType': 'Mixed', 'NonSym': True})
        self.assertEqual(c.types['FaceFitSkeleton.NonSym'], 'bool')
        self.assertEqual(c.enums['FaceFitSkeleton.RigType'], ('Joints', 'BlendShapes', 'Mixed'))
        self.assertEqual(c.values['FaceFitSkeleton.NonSymSide'], '')
        self.assertEqual(host.sides, [])

    def test_only_non_sym_callback_changes_active_side(self):
        host = OptionsHost()
        SetOriginalFaceOptions(host).apply({'NonSym': True})
        self.assertEqual(host.sides, [])
        SetOriginalFaceOptions(host).apply({'NonSym': False}, switch_side=True)
        self.assertEqual(host.sides, [2])

    def test_pre_mask_settings_are_not_written_to_an_invented_container(self):
        host = OptionsHost(fit=False)
        self.assertIsNone(SetOriginalFaceOptions(host).apply({'LipCtrls': '24'}))
        self.assertEqual(host._cmds.calls, [])

    def test_invalid_options_are_rejected_before_any_scene_edit(self):
        for values in ({'MaxInf': 8}, {'Phonemes': 1}, {'invented': True}, {'RigType': 'Other'}):
            host = OptionsHost()
            with self.assertRaises(ValueError):
                SetOriginalFaceOptions(host).apply(values)
            self.assertEqual(host._cmds.calls, [])
