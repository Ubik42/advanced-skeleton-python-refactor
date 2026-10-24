"""Playback-range Bake follows the source loop, not a highlighted switch."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from adv_py.adapters.maya_original_animation_bake import MayaOriginalAnimationBakeMixin
from adv_py.adapters.maya_source_limb_matching import original_baking_mocap


class BakeCommands:
    def __init__(self): self.time=20.; self.auto=False; self.events=[]; self.cancel=False
    def objExists(self, node):
        from adv_py.core.character_registry import REGISTRY_NAME
        return node == REGISTRY_NAME
    def playbackOptions(self, **flags): return 1.5 if flags.get('minTime') else 3.
    def autoKeyframe(self, **flags):
        if flags.get('query'): return self.auto
        self.auto=flags['state']; self.events.append(('auto', self.auto))
    def currentTime(self, value=None, **flags):
        if flags.get('query'): return self.time
        self.time=value; self.events.append(('time', value))
    def optionVar(self, **flags): return 1
    def checkBox(self, name, **flags): return True
    def setAttr(self, plug, value): self.events.append(('set', plug, value))
    def progressBar(self, name, **flags):
        if flags.get('query'): return self.cancel
        self.events.append(('progress', name, flags))


class Host(MayaOriginalAnimationBakeMixin):
    def __init__(self): self._cmds=BakeCommands(); self.saved=object()
    def _require_transaction(self): pass
    def read_character_registration(self): return self.saved
    def original_control_sets(self, name='', **state): return ('ControlSet',)


class OriginalAnimationBakeTests(unittest.TestCase):
    def test_mocap_matching_uses_live_checkbox_even_when_saved_option_is_stale(self):
        for exists,value in ((False,True),(True,False),(True,True)):
            with self.subTest(exists=exists,value=value):
                class UI:
                    def optionVar(self,**flags):raise AssertionError('Source explicitly excludes optionVar for matching')
                    def checkBox(self,name,**flags):return exists if flags.get('exists') else value
                self.assertEqual(original_baking_mocap(UI()),exists and value)

    def test_multi_rp_playback_bake_switches_once_then_forces_each_frame(self):
        host=Host(); c=host._cmds
        bindings={name:[('rp', name, 'FKIK'+name+'.FKIKBlend')] for name in ('Arm_R','Leg_L')}
        with patch('adv_py.adapters.maya_original_animation_bake._bindings', return_value=bindings), \
             patch('adv_py.adapters.maya_source_limb_matching.switch') as switch, \
             patch('adv_py.adapters.maya_source_limb_matching.apply',
                   side_effect=lambda host,saved,binding,mode,**flags:c.events.append(('align',binding,c.time,flags))):
            frames=host.bake_original_fkik_animation('Arm_R|Leg_L', 'ik')
        self.assertEqual(frames,(1.5,2.5,3.5))
        self.assertEqual(switch.call_count,2)
        self.assertTrue(all(call.kwargs['baking_mocap'] for call in switch.call_args_list))
        aligns=[row for row in c.events if row[0]=='align']
        self.assertEqual([(row[1],row[2]) for row in aligns],
            [('Arm_R',1.5),('Leg_L',1.5),('Arm_R',2.5),('Leg_L',2.5),('Arm_R',3.5),('Leg_L',3.5)])
        self.assertTrue(all(row[3]==dict(align_only=True,force=True,baking=True,baking_mocap=True) for row in aligns))
        self.assertEqual((c.time,c.auto),(20.,False))

    def test_fk_bake_initializes_original_ten_endpoint_and_retains_existing_autokey(self):
        host=Host(); c=host._cmds; c.auto=True
        with patch('adv_py.adapters.maya_original_animation_bake._bindings',
                   return_value={'Leg_R':[('rp','leg','mode.FKIKBlend')]}), \
             patch('adv_py.adapters.maya_source_limb_matching.switch'), \
             patch('adv_py.adapters.maya_source_limb_matching.apply'):
            host.bake_original_fkik_animation('Leg_R','fk',baking_mocap=False)
        self.assertIn(('set','mode.FKIKBlend',10),c.events)
        self.assertTrue(c.auto)

    def test_cancelled_progress_restores_clock_autokey_and_ends_progress(self):
        host=Host(); c=host._cmds; c.cancel=True
        with patch('adv_py.adapters.maya_original_animation_bake._bindings',
                   return_value={'Arm_R':[('rp','arm','mode.FKIKBlend')]}), \
             patch('adv_py.adapters.maya_source_limb_matching.switch'):
            with self.assertRaisesRegex(RuntimeError,'Interrupted'):
                host.bake_original_fkik_animation('Arm_R','ik',progress='main')
        self.assertEqual((c.time,c.auto),(20.,False))
        self.assertEqual(c.events[-1],('progress','main',{'edit':True,'endProgress':True}))

    def test_spline_bake_refreshes_translation_registration_then_uses_same_loop(self):
        host=Host(); c=host._cmds
        changed=object()
        host.enable_source_spline_first_translation=lambda saved:changed
        host.switch_source_character_spline=lambda saved,binding,mode:c.events.append(('switch_spline',saved,mode))
        host.align_source_character_spline=lambda saved,binding,mode,**flags:c.events.append(('align_spline',saved,c.time,flags))
        with patch('adv_py.adapters.maya_original_animation_bake._bindings',
                   return_value={'Spine_M':[('spline','spine','mode.FKIKBlend')]}):
            host.bake_original_fkik_animation('Spine_M','ik',baking_mocap=False)
        self.assertIn(('switch_spline',changed,'ik'),c.events)
        self.assertEqual([row[2] for row in c.events if row[0]=='align_spline'],[1.5,2.5,3.5])


if __name__=='__main__':unittest.main()
