"""Preserved property creation and temporary lock restoration contracts."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from adv_py.adapters.maya_character_properties import install
from adv_py.adapters.maya_character_transfer import _writable_connection
from adv_py.core.character_preservation import PreservedExtension


class CharacterPropertyTests(unittest.TestCase):
    def test_definition_preserves_nonsequential_enum_and_unset_string(self):
        commands=Mock()
        commands.objExists.return_value=False
        attributes=(
            ('mode','enum',9,True,True,(('niceName','Mode'),('enum',('Manual=0:Auto=7:Done=9',)),('default',(7,)),('channelBox',True))),
            ('note','string',None,True,False,(('niceName','Note'),('channelBox',False))),
        )
        row=PreservedExtension('|control','id','transform',None,None,attributes,())
        install(SimpleNamespace(_cmds=commands),(row,))
        commands.addAttr.assert_any_call('|control',longName='mode',niceName='Mode',keyable=True,
            attributeType='enum',enumName='Manual=0:Auto=7:Done=9',defaultValue=7)
        # Unset strings must remain unset; applying locks here would prevent wiring.
        self.assertEqual(commands.setAttr.call_count,2)
        commands.setAttr.assert_any_call('|control.mode',9)
        commands.setAttr.assert_any_call('|control.note',channelBox=False)

    def test_destination_locks_restore_on_failed_rewire_without_locking_unlocked_plugs(self):
        commands=Mock()
        commands.getAttr.side_effect=lambda plug,**kwargs:plug=='old.input'
        with self.assertRaisesRegex(RuntimeError,'injected'):
            with _writable_connection(commands,'old.input','new.input','old.input'):
                raise RuntimeError('injected')
        self.assertEqual(commands.setAttr.call_args_list,[
            unittest.mock.call('old.input',lock=False),unittest.mock.call('old.input',lock=True)])
