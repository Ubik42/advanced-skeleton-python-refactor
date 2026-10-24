"""ADV label lookup and visible/custom Maya label behavior."""
import unittest

from adv_py.adapters.maya_fit import MayaFitJointHost
from adv_py.core.joint_labels import JointLabel
from adv_py.core.source_fit_labels import source_fit_label_code, source_fit_label_text


class Commands:
    def __init__(self, code=18, text='', visible=True):
        self.values = {'|Joint.type': code, '|Joint.otherType': text,
                       '|Joint.drawLabel': visible}

    def getAttr(self, plug):
        return self.values[plug]

    def setAttr(self, plug, value, **options):
        self.values[plug] = value


def host(commands):
    result = MayaFitJointHost.__new__(MayaFitJointHost)
    result._cmds = commands
    result._transaction_active = True
    result._transaction_changed = False
    return result


class SourceFitLabelTests(unittest.TestCase):
    def test_source_builtin_palette_and_custom_codes(self):
        for label, code in (('Root',1),('Hip',2),('Foot',4),('Shoulder',10),('Hand',12),
                            ('ToesEnd',18),('Neck',18),('Knee',18),('root',18)):
            self.assertEqual(source_fit_label_code(label), code)

    def test_other_empty_is_empty_and_unknown_builtin_codes_are_ignored(self):
        self.assertEqual(source_fit_label_text(18, visible=True), '')
        for code in (3,5,6,7,8,9,11,13,14,19):
            self.assertEqual(source_fit_label_text(code, visible=True), '')

    def test_hidden_root_has_no_label_and_custom_text_is_not_trimmed(self):
        self.assertEqual(source_fit_label_text(1, visible=False), '')
        self.assertEqual(source_fit_label_text(18, visible=True, other_type=' Root '), ' Root ')
        self.assertEqual(source_fit_label_text(0, visible=True), 'None')

    def test_host_custom_label_round_trip_uses_other_instead_of_maya_knee_enum(self):
        commands = Commands()
        adapter = host(commands)
        adapter.set_joint_label('|Joint', JointLabel('Knee'))
        self.assertEqual(commands.values['|Joint.type'], 18)
        self.assertEqual(adapter.read_joint_label('|Joint'), JointLabel('Knee'))

    def test_host_returns_no_label_for_visible_empty_other_or_unknown_enum(self):
        for commands in (Commands(), Commands(code=3), Commands(code=1, visible=False)):
            self.assertIsNone(host(commands).read_joint_label('|Joint'))

    def test_host_preserves_raw_custom_label_from_an_existing_source_scene(self):
        self.assertEqual(host(Commands(text=' 0Spine ')).read_joint_label('|Joint'),
                         JointLabel(' 0Spine '))


if __name__ == '__main__':
    unittest.main()
