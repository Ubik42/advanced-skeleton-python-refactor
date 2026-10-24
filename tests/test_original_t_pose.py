"""Source T-pose orchestration uses real RP alignment and Extra layers."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from adv_py.adapters.maya_original_t_pose import apply
from adv_py.adapters.maya_original_driver_attributes import MayaOriginalDriverAttributesMixin


class PoseCommands:
    def __init__(self):
        self.events = []
        self.missing = set()
    def objExists(self, node):
        return node not in self.missing
    def xform(self, node, **flags):
        self.events.append(('xform', node, flags))
        if flags.get('query'):
            return (1, 2, 3) if flags.get('translation') else (4, 5, 6)
    def setAttr(self, plug, value):
        self.events.append(('set', plug, value))
    def warning(self, message):
        self.events.append(('warning', message))


class OriginalTPoseTests(unittest.TestCase):
    def host(self, c):
        return SimpleNamespace(_cmds=c, _require_transaction=lambda: None,
            align_source_character_limb=lambda saved, binding, mode:
                c.events.append(('align', binding.label, binding.side, mode)))

    def binding(self, saved, label, side):
        return SimpleNamespace(label=label, side=side,
            ik_control='IK' + label + '_' + side,
            pole_control='Pole' + label + '_' + side)

    def run_pose(self, c):
        with patch('adv_py.adapters.maya_original_t_pose.registration', return_value=object()), \
             patch('adv_py.adapters.maya_original_t_pose.resolve_source_limb', side_effect=self.binding), \
             patch('adv_py.adapters.maya_original_t_pose.source_control_from_role', side_effect=lambda host, role: role):
            return apply(self.host(c))

    def test_both_sides_align_leg_then_arm_and_move_only_source_extra_layers(self):
        c = PoseCommands()
        self.assertEqual(self.run_pose(c), ('R', 'L'))
        self.assertEqual([row for row in c.events if row[0] == 'align'], [
            ('align', 'Leg', 'R', 'ik'), ('align', 'Arm', 'R', 'ik'),
            ('align', 'Leg', 'L', 'ik'), ('align', 'Arm', 'L', 'ik')])
        self.assertIn(('xform', 'FKExtraHip_R', {'worldSpace': True, 'rotation': (0, -90, -88)}), c.events)
        self.assertIn(('xform', 'FKExtraHip_L', {'worldSpace': True, 'rotation': (0, -90, 92)}), c.events)
        self.assertIn(('xform', 'IKExtraLeg_R', {'objectSpace': True,
            'translation': (1, 2, 3), 'rotation': (4, 5, 6)}), c.events)
        self.assertEqual([row[1] for row in c.events if row[0] == 'set'],
            ['PoleExtraArm_R.tx', 'PoleExtraArm_R.tz', 'PoleExtraArm_L.tx', 'PoleExtraArm_L.tz'])

    def test_missing_left_required_layer_keeps_completed_right_side_and_warns(self):
        c = PoseCommands(); c.missing.add('FKExtraKnee_L')
        self.assertEqual(self.run_pose(c), ('R',))
        self.assertTrue(c.events[-1][1].startswith('Required node: "FKExtraKnee_L"'))
        self.assertFalse(any(row[0] == 'align' and row[2] == 'L' for row in c.events))

    def test_source_role_mapping_uses_existing_python_layers(self):
        c = PoseCommands(); host = self.host(c)
        with patch('adv_py.adapters.maya_original_t_pose.registration', return_value=object()), \
             patch('adv_py.adapters.maya_original_t_pose.resolve_source_limb', side_effect=self.binding), \
             patch('adv_py.adapters.maya_original_t_pose.source_control_from_role',
                   side_effect=lambda host, role: 'Actual_' + role):
            apply(host)
        self.assertIn(('set', 'Actual_PoleExtraArm_L.tz', 0), c.events)
        self.assertTrue(host._transaction_changed)

    def test_build_pose_places_t_pose_before_gui_and_fit_override(self):
        from test_original_build_pose_restore import NativePoseCommands
        c = NativePoseCommands()
        class Host(MayaOriginalDriverAttributesMixin):
            _cmds = c
            def _require_transaction(self): pass
            def read_body_build_pose(self): raise AssertionError('source commands only')
            def read_face_build_pose(self): raise AssertionError('source commands only')
        with patch('adv_py.adapters.maya_original_control_identity.source_control_from_role',
                   side_effect=lambda host, role: 'AdvPy_WristFK_R' if role == 'FKWrist_R' else role), \
             patch('adv_py.adapters.maya_original_t_pose.apply', side_effect=lambda host: c.events.append(('tpose',))):
            Host().go_to_original_corrective_build_pose(face=False, t_pose=True)
        extra = c.events.index(('set', 'AdvPy_WristFK_R.rotateX', 1.))
        tpose = c.events.index(('tpose',))
        gui = c.events.index(('set', 'CTRL_smile.translateX', 0))
        run = c.events.index(('set', 'CTRL_smile.translateX', 3.))
        self.assertLess(extra, tpose); self.assertLess(tpose, gui); self.assertLess(gui, run)


if __name__ == '__main__': unittest.main()
