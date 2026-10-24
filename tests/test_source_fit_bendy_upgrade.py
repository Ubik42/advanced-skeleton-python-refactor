"""Build-time legacy Fit decisions and original first-joint count policy."""
from types import SimpleNamespace
import unittest

from adv_py.adapters.maya_source_fit_bendy_upgrade import upgrade
from adv_py.adapters.maya_fit import MayaFitJointHost
from adv_py.core.fit_settings import FitSkeletonValidationError


class Commands:
    def __init__(self):
        self.attrs={'A.bendyJoints':True,'A.twistJoints':3,
            'B.bendyJoints':False,'B.twistJoints':7,'B.partControllers':True,
            'C.bendyCtrls':4,'C.twistJoints':6,'FitSkeleton.numMainExtras':2}
        self.events=[]
    def listRelatives(self,*args,**flags):return ['A','B','C']
    def attributeQuery(self,attr,*,node,**flags):return node+'.'+attr in self.attrs
    def getAttr(self,plug,**flags):return self.attrs[plug]
    def setAttr(self,plug,value):self.attrs[plug]=value;self.events.append(('set',plug,value))
    def select(self,*nodes,**flags):self.events.append(('select',nodes))
    def refresh(self):self.events.append(('refresh',))
    def optionMenu(self,*nodes,**flags):return False
    def deleteAttr(self,plug):del self.attrs[plug];self.events.append(('delete',plug))
    def addAttr(self,node,**flags):self.attrs[node+'.'+flags['longName']]=flags['defaultValue']


class SourceFitBendyUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.c=Commands();self.host=SimpleNamespace(_cmds=self.c,_require_transaction=lambda:None)
    def test_yes_upgrades_even_disabled_old_entries_with_first_enabled_count(self):
        self.assertEqual(upgrade(self.host,answer='Yes'),('A','B'))
        for joint in ('A','B'):
            self.assertEqual(self.c.attrs[joint+'.twistJoints'],3)
            self.assertEqual(self.c.attrs[joint+'.bendyCtrls'],1)
            self.assertNotIn(joint+'.bendyJoints',self.c.attrs)
        self.assertNotIn('B.partControllers',self.c.attrs)
        self.assertEqual(self.c.attrs['C.bendyCtrls'],4)
        self.assertEqual(self.c.attrs['C.twistJoints'],6)
    def test_no_keeps_original_attributes_without_inventing_bendy_controllers(self):
        before=dict(self.c.attrs)
        self.assertEqual(upgrade(self.host,answer='No'),())
        self.assertEqual(self.c.attrs,before)
        self.assertFalse(any(event[0] in ('set','delete') for event in self.c.events))
    def test_cancel_stops_build_without_editing_attributes(self):
        before=dict(self.c.attrs)
        with self.assertRaises(FitSkeletonValidationError):upgrade(self.host,answer='Cancel')
        self.assertEqual(self.c.attrs,before)
    def test_no_enabled_legacy_joint_is_a_no_op(self):
        self.c.attrs['A.bendyJoints']=False
        self.assertEqual(upgrade(self.host),())
        self.assertEqual(self.c.events,[])
    def test_main_extras_root_zero_overrides_legacy_container_count(self):
        host=SimpleNamespace(_attribute_exists=lambda node,attr:node+'.'+attr in self.c.attrs,
            _optional_number=lambda node,attr,kind:kind(self.c.attrs[node+'.'+attr]) if node+'.'+attr in self.c.attrs else None)
        read=lambda:MayaFitJointHost.read_source_main_extras(host,'FitSkeleton','Root')
        self.assertEqual(read(),2)
        self.c.attrs['Root.numMainExtras']=0
        self.assertEqual(read(),0)
        self.c.attrs['Root.numMainExtras']=4
        self.assertEqual(read(),4)


if __name__=='__main__':unittest.main()
