"""Native control-set routing and the clean operation's mutation boundary."""
from unittest.mock import patch
import unittest
from adv_py.adapters.maya_original_control_sets import MayaOriginalControlSetsMixin


class Commands:
    def __init__(self):
        self.selection = ['FaceControl']
        self.choice = 'Yes'
        self.events = []
        self.names = {'ControlSet', 'FaceControlSet', 'ArmsControlSet'}
    def objExists(self, node): return node in self.names
    def ls(self, **flags): return list(self.selection)
    def sets(self, node, **flags): return node == 'FaceControl' and flags.get('isMember') == 'FaceControlSet'
    def select(self, nodes=(), **flags):
        self.events.append(('select', tuple(nodes), flags)); self.selection = list(nodes)
    def confirmDialog(self, **flags):
        self.events.append(('confirm', flags)); return self.choice
    def delete(self, **flags): self.events.append(('delete', flags))
    def text(self, node, **flags): return False
    def tabLayout(self, node, **flags): return False
    def menuItem(self, node, **flags): return False
    def getModifiers(self): return 4
    def warning(self, message): self.events.append(('warning', message))


class Host(MayaOriginalControlSetsMixin):
    def __init__(self): self._cmds = Commands()
    def _require_transaction(self): pass
    def go_to_original_corrective_build_pose(self, **flags):
        self._cmds.events.append(('pose', flags)); return ()


class OriginalControlSetsTests(unittest.TestCase):
    def test_first_selected_face_member_overrides_body_default(self):
        host = Host()
        self.assertEqual(host.original_control_sets(), ('FaceControlSet',))
        host._cmds.selection = ['Mesh', 'FaceControl']
        self.assertEqual(host.original_control_sets(), ('ControlSet',))
        host._cmds.selection = []
        self.assertEqual(host.original_control_sets(), ('ControlSet',))
        self.assertEqual(host.original_control_sets('bodySetup'), ('ControlSet',))

    def test_source_selector_and_picker_authored_state(self):
        host = Host()
        self.assertEqual(host.original_control_sets('selector1',
            selector_sets='ArmsControlSet Missing FaceControlSet'), ('ArmsControlSet', 'FaceControlSet'))
        self.assertEqual(host.original_control_sets('asPicker', picker_tab='character_face'), ('FaceControlSet',))

    def test_cancellation_does_not_capture_or_mutate_native_animation(self):
        host = Host(); host._cmds.choice = 'No'
        with patch('adv_py.adapters.maya_static_animation_boundary.capture') as capture:
            self.assertEqual(host.clean_original_control_animation(), ())
        capture.assert_not_called()
        self.assertEqual([row[0] for row in host._cmds.events], ['confirm'])
        self.assertFalse(hasattr(host, '_transaction_changed'))

    def test_native_clean_selects_set_uses_exact_flags_and_restores_selection(self):
        host = Host()
        with patch('adv_py.adapters.maya_original_control_identity.registration', return_value=None), \
             patch('adv_py.adapters.maya_static_animation_boundary.capture', return_value='snapshot') as capture, \
             patch('adv_py.adapters.maya_static_animation_boundary.finish') as finish:
            self.assertEqual(host.clean_original_control_animation(), ('FaceControlSet',))
        capture.assert_called_once_with(host); finish.assert_called_once_with(host, 'snapshot')
        self.assertIn(('delete', {'staticChannels': True, 'unitlessAnimationCurves': False,
            'hierarchy': 'none', 'controlPoints': False, 'shape': True}), host._cmds.events)
        self.assertEqual(host._cmds.selection, ['FaceControl'])

    def test_failed_graph_refresh_still_restores_selection_and_propagates(self):
        host = Host()
        with patch('adv_py.adapters.maya_original_control_identity.registration', return_value=None), \
             patch('adv_py.adapters.maya_static_animation_boundary.capture', return_value='snapshot'), \
             patch('adv_py.adapters.maya_static_animation_boundary.finish', side_effect=ValueError('changed UUID')):
            with self.assertRaisesRegex(ValueError, 'changed UUID'):
                host.clean_original_control_animation()
        self.assertEqual(host._cmds.selection, ['FaceControl'])

    def test_public_reset_uses_selected_set_and_control_modifier(self):
        host = Host()
        self.assertEqual(host.go_to_original_control_build_pose(t_pose=True), ())
        self.assertIn(('pose', {'face': True, 't_pose': True, 'preserve_main': True}), host._cmds.events)

    def test_original_mirror_reads_options_window_then_saved_options_and_selection(self):
        host=Host();c=host._cmds
        values={'asMOSide':'asMOSideL2R','asMOSpace':'asMOSpaceCenter',
                'asMOAxis':'asMOAxisZ','asMOSelOnly':'asMOSelOnlySel'}
        c.window=lambda name,**flags:True
        c.radioCollection=lambda name,**flags:values[name.removesuffix('RadioCollection')]
        def option(**flags):
            if 'stringValue' in flags:
                name,value=flags['stringValue'];values[name]=value
            elif 'exists' in flags:return flags['exists'] in values
            else:return values[flags['query']]
        c.optionVar=option
        with patch('adv_py.adapters.maya_original_control_mirror.mirror_original_controls',return_value=9) as mirror:
            self.assertEqual(host.mirror_original_control_pose('faceSetup'),9)
        mirror.assert_called_once_with(host,['FaceControl'],side='L2R',space='Center',axis='Z',
                                       ui_name='faceSetup',ui_state={})


if __name__ == '__main__': unittest.main()
