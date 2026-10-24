"""A sparse original named pose must leave unrelated channels untouched."""
from types import SimpleNamespace
import unittest
from adv_py.adapters.maya_original_pose_functions import MayaOriginalPoseFunctionsMixin
from adv_py.adapters.maya_original_driver_attributes import MayaOriginalDriverAttributesMixin


class Commands:
    def __init__(self):
        self.values = {'FitSkeleton.wave':'setAttr FKWrist_R.rotateZ 30;',
                       'FKWrist_R.rotateZ':0., 'FKShoulder_R.rotateX':25.}
        self.choice='Cancel'; self.events=[]
    def objExists(self, node): return node in self.values or node in ('FitSkeleton','FKWrist_R','FKShoulder_R')
    def getAttr(self, plug, **flags): return self.values[plug]
    def setAttr(self, plug, value, **flags): self.values[plug]=value
    def confirmDialog(self, **flags): self.events.append(flags); return self.choice


class Host(MayaOriginalPoseFunctionsMixin,MayaOriginalDriverAttributesMixin):
    def __init__(self): self._cmds=Commands()
    def _require_transaction(self): pass
    def original_stored_pose_names(self): return ('wave',)
    def go_to_original_corrective_build_pose(self): raise AssertionError('Original named pose does not reset the Body')


class OriginalNamedPoseTests(unittest.TestCase):
    def test_sparse_pose_sets_only_authored_channels_without_resetting_body(self):
        host=Host()
        self.assertEqual(host.apply_original_named_pose('wave'),'wave')
        self.assertEqual(host._cmds.values['FKWrist_R.rotateZ'],30.)
        self.assertEqual(host._cmds.values['FKShoulder_R.rotateX'],25.)

    def test_cancelled_pose_add_does_not_read_channels_or_create_run(self):
        host=Host()
        self.assertEqual(host.add_original_build_pose_channels(('MissingControl',),('rotateX',)),0)
        self.assertFalse(hasattr(host,'_transaction_changed'))
        self.assertNotIn('FitSkeleton.run',host._cmds.values)
        dialog=host._cmds.events[0]
        self.assertEqual(dialog['defaultButton'],'Cancel')
        self.assertIn('MissingControl.rotateX',dialog['message'])


if __name__=='__main__':unittest.main()
