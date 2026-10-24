"""Coupled IKX reads must follow preceding FK writes, as in original MEL."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from adv_py.adapters.maya_source_limb_matching import _align_fk_original
from adv_py.adapters.maya_source_limb_matching import _align_ik_rotation


class CoupledCommands:
    def __init__(self):self.stage=0;self.events=[]
    def xform(self,node,**flags):
        if flags.get('query'):
            self.events.append(('read',node,self.stage,flags))
            return (float(self.stage),0.,0.) if flags.get('rotation') else (float(self.stage),1.,2.)
        self.events.append(('write',node,flags))
        if flags.get('rotation'):self.stage+=1
    def getAttr(self,plug,**flags):
        self.events.append(('scale',plug,self.stage));return [(1.,1.,1.)]
    def objExists(self,node):return False


class SourceRPAlignOrderTests(unittest.TestCase):
    def test_qtoes_override_keeps_end_frame_rotate_order_and_is_read_after_it(self):
        events=[]
        class Commands:
            def objExists(self,node):return True
            def xform(self,node,**flags):
                events.append((node,flags))
                if flags.get('rotateOrder') is True:return 'yzx'
                if flags.get('query'):return (1,2,3) if node=='EndAlign' else (4,5,6)
        _align_ik_rotation(Commands(),'IKLeg','EndAlign','QAlign')
        self.assertEqual(events,[('IKLeg',{'query':True,'rotateOrder':True}),
            ('EndAlign',{'preserve':True,'rotateOrder':'yzx'}),
            ('EndAlign',{'query':True,'worldSpace':True,'rotation':True}),
            ('QAlign',{'query':True,'worldSpace':True,'rotation':True}),
            ('IKLeg',{'worldSpace':True,'rotation':(4,5,6)})])

    def test_downstream_ikx_rotation_is_evaluated_after_upstream_fk_rotation(self):
        c=CoupledCommands(); host=SimpleNamespace(_cmds=c)
        joints=tuple(SimpleNamespace(body=name,fk_driver='FKX'+name,ik_driver='IKX'+name,
                                    control='FK'+name) for name in ('Shoulder','Elbow','Wrist'))
        binding=SimpleNamespace(joints=joints,middle_index=1,primary_count=3,toe_control=None,
                                toe_source=None,hybrid_controls=(),reverse_roll=None,ik_control='IKArm')
        with patch('adv_py.adapters.maya_source_limb_matching._set'), \
             patch('adv_py.adapters.maya_source_spline_matching._custom_orient'):
            _align_fk_original(host,None,binding)
        rotations=[row for row in c.events if row[0]=='write' and 'rotation' in row[2]]
        self.assertEqual([row[2]['rotation'][0] for row in rotations],[0.,1.,2.])
        scale_reads=[row for row in c.events if row[0]=='scale']
        self.assertEqual(scale_reads,[('scale','Shoulder.scale',3),('scale','Elbow.scale',3)])
        # Source does not read the Body end scale in this direction. Export
        # cleanup can retire the Wrist Body while the IK control stays alive.
        self.assertFalse(any(row[0]=='scale' and row[1]=='Wrist.scale' for row in c.events))
        end_scale=next(row for row in c.events if row[0]=='read' and row[1]=='IKArm')
        self.assertEqual(end_scale[2],3)


if __name__=='__main__':unittest.main()
