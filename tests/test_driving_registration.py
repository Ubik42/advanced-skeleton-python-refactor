import unittest
from adv_py.adapters.maya_driving_registration import _command_addresses,_scale_record_edges
from adv_py.core.character_registry import canonical
from adv_py.core.source_body_matrix import decode_source_body_matrix


class DrivingRegistrationTests(unittest.TestCase):
    def test_sdk_readdresses_saved_commands_at_exact_dag_boundary(self):
        before='|hero:Group|hero:Extra'
        after='|hero:Group|hero:SDKControl|hero:Extra'
        source='setAttr "'+before+'|hero:Control.rotateX" 0;setAttr '+before+'Sibling.rotateX 5;'
        expected='setAttr "'+after+'|hero:Control.rotateX" 0;setAttr '+before+'Sibling.rotateX 5;'
        self.assertEqual(_command_addresses(source,((before,after),)),expected)

    def test_scale_record_changes_only_source_replaced_outgoing_edge(self):
        control='|Controls|FKElbow_R';body='|Root_M|Elbow_R'
        descriptor=dict(name='SDKFKElbow_RScaleMPD',kind='multiplyDivide',
            values=[['operation',1.]],connections=[[control+'.scale','input1'],
                                                    ['|SDKFKElbow_R.scale','input2']])
        edges=tuple((control+'.scale'+axis,body+'.scale'+axis,
                     descriptor['name']+'.output'+axis) for axis in 'XYZ')
        raw=dict(body=body,nodes=[],outputs=[[control+'.scale'+axis,body+'.scale'+axis]
                                            for axis in 'XYZ'])
        updated,touched=_scale_record_edges(raw,edges,descriptor)
        self.assertTrue(touched)
        graph=decode_source_body_matrix(canonical(updated))
        self.assertEqual(len(graph.nodes),1)
        self.assertEqual(graph.outputs[0][0],descriptor['name']+'.outputX')
        untouched=dict(outputs=[[control+'.scaleX','|Other.scaleX']])
        self.assertEqual(_scale_record_edges(untouched,edges,descriptor),(untouched,False))
