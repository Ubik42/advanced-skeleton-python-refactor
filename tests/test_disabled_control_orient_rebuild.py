"""Native disabled/custom orientation frames survive mirrored rebuilding."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from adv_py.adapters.maya_control_orient_rebuild import (
    OriginalOrientRebuildRow,capture,restore,retained_disabled_root)
from adv_py.adapters.maya_original_pose_functions import MayaOriginalPoseFunctionsMixin
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.original_control_orientation import OriginalControlOrientOptions

MATRIX=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,2.,0.,0.,1.)


class DisabledOrientTests(unittest.TestCase):
    def commands(self):
        class Commands:
            disabled=True
            values={}
            writes=[]
            def objExists(self,node):
                if node=='asControlOrientDetachParentHolder':return False
                if node=='CustomOrientsDisabled':return self.disabled
                return True
            def sets(self,node,**flags):
                return True if flags.get('isMember') else ['FKWrist_R','FKWrist_L']
            def getAttr(self,plug,**flags):
                if flags.get('asString'):return 'X' if plug.endswith('primaryAxis') else 'Y'
                if plug.endswith('customAxis'):return False
                return plug.endswith('mirror')
            def xform(self,node,**flags):
                if flags.get('query'):return MATRIX
                self.writes.append((node,flags))
            def setAttr(self,*args,**flags):self.writes.append((args,flags))
            def addAttr(self,*args,**flags):self.writes.append((args,flags))
        return Commands()

    def test_capture_disabled_primary_axes_preserves_both_actual_frames_without_custom_axis(self):
        c=self.commands()
        host=SimpleNamespace(_cmds=c)
        with patch('adv_py.adapters.maya_control_orient_rebuild.source_control_name',side_effect=lambda host,node:node):
            rows=capture(host,SimpleNamespace())
        self.assertEqual(tuple(row.custom_matrix for row in rows),(MATRIX,MATRIX))
        self.assertEqual(tuple(row.reverse_matrix for row in rows),(MATRIX,MATRIX))
        self.assertEqual(tuple(row.custom_axis for row in rows),(False,False))

    def test_each_mirrored_restore_receives_all_saved_frames_and_keeps_primary_axis_metadata(self):
        c=self.commands()
        registration=SimpleNamespace(nodes=())
        host=SimpleNamespace(_cmds=c,_require_transaction=lambda:None,
            read_character_registration=lambda:registration)
        options=OriginalControlOrientOptions(mirror=True)
        rows=(OriginalOrientRebuildRow('FKWrist_R',options,MATRIX,False,MATRIX),
              OriginalOrientRebuildRow('FKWrist_L',options,MATRIX,False,MATRIX))
        calls=[]
        def set_axis(host,controls,settings,**kwargs):
            calls.append(kwargs);return controls
        with patch('adv_py.adapters.maya_control_orient_rebuild._address',side_effect=lambda host,name:name), \
             patch('adv_py.adapters.maya_control_orient_rebuild.set_original_control_orient',side_effect=set_axis):
            self.assertEqual(restore(host,rows,registration,'rig'),(registration,'rig'))
        for call in calls:
            self.assertEqual(call['custom_frames'],{'FKWrist_R':MATRIX,'FKWrist_L':MATRIX})
        self.assertFalse(any(isinstance(row[0],tuple) and row[0][0].endswith('.customAxis')
            and row[0][1] is True for row in c.writes))
        self.assertEqual({row[0] for row in c.writes if isinstance(row[0],str)},
            {'CustomOrientReverseFKWrist_R','CustomOrientReverseFKWrist_L'})

    def test_toggle_uses_original_confirmation_and_cancel_leaves_holder_untouched(self):
        for result in (0,2):
            c=self.commands();c.disabled=False
            c.ls=lambda *args,**flags:[]
            c.select=lambda *args,**flags:None
            c.createNode=lambda *args,**flags:c.writes.append(('create',flags))
            host=SimpleNamespace(_cmds=c,_require_transaction=lambda:None,
                confirm_original_control_build_pose=lambda:result)
            count=MayaOriginalPoseFunctionsMixin.toggle_original_custom_orients(host,False)
            self.assertEqual(count,0)
            self.assertEqual(any(row[0]=='create' for row in c.writes),bool(result))

    def test_disabled_holder_requires_known_actual_frame_and_literal_native_restore_attribute(self):
        c=SimpleNamespace(objExists=lambda name:True,ls=lambda *args,**flags:['|CustomOrientsDisabled'],
            nodeType=lambda node:'transform',listAttr=lambda *args,**flags:['CustomOrientFKWrist_R_rx'],
            getAttr=lambda plug:12.,connectionInfo=lambda *args,**flags:'')
        host=SimpleNamespace(_cmds=c)
        saved=SimpleNamespace(nodes=())
        with patch('adv_py.adapters.maya_original_control_identity.control_roles',return_value={'wrist':'FKWrist_R'}):
            self.assertEqual(retained_disabled_root(host,saved),('|CustomOrientsDisabled',))
            c.listAttr=lambda *args,**flags:['CustomOrientFKWrist_R_rx_extra']
            with self.assertRaises(CharacterRegistryError):retained_disabled_root(host,saved)


if __name__=='__main__':unittest.main()
