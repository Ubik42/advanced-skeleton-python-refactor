"""Matching must sample the evaluated scene in the MEL operation order."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from adv_py.adapters.maya_source_spline_matching import align


class Commands:
    def __init__(self):
        self.calls=[];self.moved=0;self.live={'DeformationSystem'};self.auto=True
    def ls(self,*args,**flags):return []
    def select(self,*args,**flags):self.calls.append(('select',args,flags))
    def autoKeyframe(self,**flags):
        if flags.get('query'):return self.auto
        self.auto=flags['state']
    def objExists(self,node):
        return node in self.live or node.startswith('|FK') or node.startswith('|Driver')
    def sets(self,node,**flags):return node!='|FK2'
    def xform(self,node,**flags):
        self.calls.append(('xform',node,flags))
        if flags.get('query'):
            if flags.get('rotation'):return (1. if node=='|D|A_M' else 2.,0.,0.)
            if node=='|Driver1':return (float(self.moved),0.,0.)
            if node=='|D|A_M':return (0. if self.moved==0 else 100.,0.,0.)
            if node=='|D|B_M':return (100. if self.moved==0 else 0.,0.,0.)
            return (0.,0.,0.)
        if node.startswith('|Hybrid') or node=='|FK0':self.moved+=1
    def listRelatives(self,node,**flags):
        return ['|D|A_M','|D|B_M'] if node=='DeformationSystem' else ['|CurveShape']
    def curve(self,**flags):self.live.add('FK2IKCurve');return 'FK2IKCurve'
    def rebuildCurve(self,curve,**flags):return [curve]
    def createNode(self,kind,**flags):self.live.add(flags['name']);return flags['name']
    def addAttr(self,*args,**flags):pass
    def setAttr(self,*args,**flags):pass
    def connectAttr(self,*args,**flags):pass
    def getAttr(self,plug,**flags):return [(0.,0.,0.)]
    def delete(self,node):self.live.remove(node)
    def warning(self,text):self.calls.append(('warning',text))


class SourceSplineNativeMatchingTests(unittest.TestCase):
    def host(self):
        return NS(_cmds=Commands(),_require_transaction=lambda:None,
                  _transaction_changed=False,namespace=None)

    def test_ik_to_fk_reads_each_driver_after_previous_two_writes(self):
        host=self.host()
        binding=NS(plan=NS(),fk_controls=('|FK0','|FK1','|FK2'),
                   ik_drivers=('|Driver0','|Driver1','|Driver2'))
        with patch('adv_py.adapters.maya_source_spline_matching._custom_orient'):
            align(host,NS(channels=()),binding,'fk')
        writes=[row for row in host._cmds.calls if row[0]=='xform' and not row[2].get('query')]
        self.assertEqual([row[1] for row in writes],['|FK0','|FK0','|FK1','|FK1'])
        self.assertEqual(writes[2][2]['translation'],(2.,0.,0.))
        self.assertTrue(host._cmds.auto)

    def test_fk_to_ik_resamples_nearest_deform_and_delays_endpoint_query(self):
        host=self.host()
        plan=NS(body_joints=('|Body|Root_M','|Body|Chest_M'),targets=('|IK0','|IK1'),
                hybrid_controls=('|Hybrid0','|Hybrid1'))
        binding=NS(plan=plan,physical_chain=plan.body_joints)
        endpoint_calls=[]
        def endpoint(host,registration,binding,index):
            endpoint_calls.append((index,host._cmds.moved));return (0.,0.,0.)
        with patch('adv_py.adapters.maya_source_spline_matching._custom_orient'),patch(
                'adv_py.adapters.maya_source_spline_matching._endpoint_rotation',side_effect=endpoint):
            align(host,NS(),binding,'ik')
        hybrids=[row for row in host._cmds.calls if row[0]=='xform'
                 and row[1].startswith('|Hybrid') and not row[2].get('query')]
        self.assertEqual([row[2]['rotation'] for row in hybrids],[(1.,0.,0.),(2.,0.,0.)])
        self.assertEqual(endpoint_calls,[(0,2),(1,2)])
        self.assertNotIn('FK2IKCurve',host._cmds.live)
        self.assertIn('tempPointOnCurveInfo',host._cmds.live)
        self.assertTrue(host._cmds.auto)


if __name__=='__main__':unittest.main()
