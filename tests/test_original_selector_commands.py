"""Source selection modifiers, Extra names and historical align directions."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from adv_py.adapters.maya_original_selector_commands import MayaOriginalSelectorCommandsMixin
from adv_py.application.original_selector import EditOriginalSelector


class Commands:
    def __init__(self):self.events=[];self.nodes={'FKExtraWrist_R','RootExtraX_M','FKWrist_R'}
    def objExists(self,name):return name in self.nodes
    def select(self,*args,**flags):self.events.append((args,flags))
    def formLayout(self,*args,**flags):return True
    def setFocus(self,name):self.events.append(('focus',name))


class Host(MayaOriginalSelectorCommandsMixin):
    def __init__(self):self._cmds=Commands()
    def _require_transaction(self):pass


class OriginalSelectorTests(unittest.TestCase):
    def test_source_extra_root_special_case_and_shift_toggle(self):
        host=Host();c=host._cmds
        with patch('adv_py.adapters.maya_original_selector_commands.source_control_name',side_effect=lambda h,n:n), \
             patch('adv_py.adapters.maya_original_selector_commands.source_control_from_role',side_effect=lambda h,n:n):
            self.assertEqual(host.resolve_original_selector_control('Default','RootX_M',extra=True),'RootExtraX_M')
            self.assertEqual(host.select_original_selector_controls('Default',('FKWrist_R',),modifiers=1,extra=True),('FKExtraWrist_R',))
        self.assertEqual(c.events,[(('FKExtraWrist_R',),{'toggle':True}),('focus','asSelectorDefaultFormLayout')])

    def test_original_align_function_names_keep_the_mel_direction(self):
        calls=[]
        host=SimpleNamespace(transaction=lambda label:nullcontext(),
            align_original_selector_fkik=lambda controls,mode,**flags:calls.append((controls,mode,flags)))
        service=EditOriginalSelector(host)
        service.execute('asAlignIK2FK','Default',('FKIKArm_R',))
        service.execute('asAlignFK2IK','Default',('FKIKArm_R',))
        self.assertEqual(calls,[(('FKIKArm_R',),'ik',{'switch':False}),(('FKIKArm_R',),'fk',{'switch':False})])
