"""Body confirmation restores original commands, GUI and expression order."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from adv_py.adapters.maya_original_build_pose_confirm import restore_original_body_build_pose
from adv_py.adapters.maya_original_driver_attributes import MayaOriginalDriverAttributesMixin


class NativePoseCommands:
    def __init__(self):
        self.events=[]
        self.values={
            'buildPose.udAttr':'setAttr FKWrist_R.rotateX 0;',
            'buildPose.udExtraAttr':'setAttr FKWrist_R.rotateX 1;',
            'FitSkeleton.run':'setAttr FKWrist_R.rotateX 5;setAttr CTRL_smile.translateX 3;',
            'FaceFitSkeleton.run':'setAttr CTRL_smile.translateX 99;',
            'AdvPy_WristFK_R.rotateX':12.,'CTRL_smile.translateX':8.,
            'CTRL_smile.scaleX':2.,'CTRL_smile.visibility':0.,'Wheel.reset':0.}
    def objExists(self,address):
        return address in self.values or address in ('buildPose','FitSkeleton','FaceFitSkeleton',
            'GRP_faceGUI','AdvPy_WristFK_R','CTRL_smile','Wheel')
    def getAttr(self,plug,**flags):
        return True if flags.get('settable') else self.values[plug]
    def setAttr(self,plug,value,**flags):
        if plug not in self.values:raise RuntimeError('missing plug')
        self.events.append(('set',plug,value));self.values[plug]=value
    def listRelatives(self,node,**flags):return ['CTRL_smile','CTRL_faceGUI_main']
    def listAttr(self,node,**flags):return ['translateX','scaleX','visibility']
    def ls(self,**flags):return ['WheelExpression_Left','otherExpression']
    def listConnections(self,node,**flags):return ['Wheel','WithoutReset']
    def currentTime(self,time=None,**flags):
        if flags.get('query'):return 12.
        self.events.append(('time',time))
    def dgdirty(self,**flags):self.events.append(('dirty',flags))
    def xform(self,node,**flags):self.events.append(('xform',node,flags))


class OriginalPoseRestoreTests(unittest.TestCase):
    def host(self,c):
        def no_python_pose():raise AssertionError('Original udAttr must not require Python pose JSON')
        return SimpleNamespace(_cmds=c,_require_transaction=lambda:None,
            read_body_build_pose=no_python_pose,read_face_build_pose=no_python_pose)

    def test_unregistered_original_body_uses_extra_commands_then_gui_wheel_and_final_run_override(self):
        c=NativePoseCommands()
        host=self.host(c)
        with patch('adv_py.adapters.maya_original_control_identity.source_control_from_role',
                   side_effect=lambda host,node:'AdvPy_WristFK_R' if node=='FKWrist_R' else node):
            self.assertEqual(restore_original_body_build_pose(host),())
        self.assertEqual(c.values['AdvPy_WristFK_R.rotateX'],5.)
        self.assertEqual(c.values['CTRL_smile.translateX'],3.)
        self.assertEqual((c.values['CTRL_smile.scaleX'],c.values['CTRL_smile.visibility']),(1,1))
        events=c.events
        gui=events.index(('set','CTRL_smile.translateX',0))
        wheel=events.index(('set','Wheel.reset',1))
        run=events.index(('set','CTRL_smile.translateX',3.))
        self.assertLess(gui,wheel);self.assertLess(wheel,run)
        self.assertEqual(events[wheel:wheel+3],[('set','Wheel.reset',1),('time',12.),('set','Wheel.reset',0)])
        self.assertTrue(host._transaction_changed)

    def test_numeric_and_xform_saved_original_roles_use_existing_python_controller(self):
        c=NativePoseCommands()
        host=self.host(c)
        parser=SimpleNamespace(_cmds=c,_original_pose_address=lambda address:
            MayaOriginalDriverAttributesMixin._original_pose_address(host,address))
        with patch('adv_py.adapters.maya_original_control_identity.source_control_from_role',
                   return_value='AdvPy_WristFK_R'):
            MayaOriginalDriverAttributesMixin._original_apply_pose_commands(parser,
                'setAttr FKWrist_R.rotateX 2;xform -os -ro 1 2 3 FKWrist_R;')
        self.assertEqual(c.values['AdvPy_WristFK_R.rotateX'],2.)
        self.assertIn(('xform','AdvPy_WristFK_R',{'objectSpace':True,'rotation':(1.,2.,3.)}),c.events)

    def test_failed_native_channel_does_not_abort_remaining_original_pose(self):
        c=NativePoseCommands();c.values['buildPose.udAttr']='setAttr missing.rotateX 2;'
        with patch('adv_py.adapters.maya_original_control_identity.source_control_from_role',
                   side_effect=lambda host,node:'AdvPy_WristFK_R' if node=='FKWrist_R' else node):
            failed=restore_original_body_build_pose(self.host(c))
        self.assertEqual(failed,('setAttr missing.rotateX 2',))
        self.assertEqual(c.values['AdvPy_WristFK_R.rotateX'],5.)


if __name__=='__main__':unittest.main()
