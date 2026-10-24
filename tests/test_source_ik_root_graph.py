from dataclasses import asdict
import unittest
from types import SimpleNamespace as Row
from unittest.mock import patch
from adv_py.core.character_registry import canonical, CharacterRegistryError
from adv_py.core.source_limb_root_frame import plan_graph
from adv_py.core.source_body_matrix import decode_source_body_matrix


class SourceIkRootGraphTests(unittest.TestCase):
    def test_fresh_offset_aligns_after_follow_outputs_and_old_offset_is_restored(self):
        from adv_py.adapters.maya_source_limb_root_frame import connect
        spec = Row(frame='|IKJoints|IKParent', parent='|IKJoints', offset='|IKJoints|IKParent|Offset',
                   source_parent='|Body|Scapula_L', source_joint='|Body|Scapula_L|Shoulder_L',
                   joint='|IKJoints|IKParent|Offset|Shoulder', rotate_order=4)
        matrix = (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,2.,0.,0.,1.)
        events = []
        c = Row(createNode=lambda *args, **flags: None, setAttr=lambda *args, **flags: None,
                connectAttr=lambda *args: events.append(('connect',args)),
                addAttr=lambda *args, **flags: None, getAttr=lambda *args: matrix,
                xform=lambda *args, **flags: events.append(('restore',args,flags)))
        host = Row(_cmds=c, _require_transaction=lambda: None, find_name_collisions=lambda name: False)
        def align(*args):
            outputs = [event for event in events if event[0]=='connect' and event[1][1].startswith(spec.frame+'.')]
            self.assertEqual(len(outputs), 12)
            events.append(('align',args))
        with patch('adv_py.adapters.maya_source_limb_root_frame.align_original_transform', side_effect=align):
            connect(host,spec,'|Body',None,use_offset_parent_matrix=False)
        self.assertEqual(events[-1][0], 'align')
        events.clear()
        with patch('adv_py.adapters.maya_source_limb_root_frame.align_original_transform') as native_align:
            connect(host,spec,'|Body',None,use_offset_parent_matrix=False,saved_offset_matrix=matrix)
            native_align.assert_not_called()
        self.assertEqual(events[-1], ('restore',(spec.offset,),dict(objectSpace=True,matrix=matrix)))

    def test_non_opm_uses_complete_native_decomposition(self):
        graph = plan_graph('|IKJoints|IKParent', '|IKJoints', '|Body|Scapula_L', 4, False)
        self.assertEqual(graph.nodes[-1].kind, 'decomposeMatrix')
        self.assertEqual(graph.nodes[-1].values, (('inputRotateOrder', 4.),))
        self.assertEqual(len(graph.outputs), 12)
        self.assertIn(('IKParentDM.outputShearZ', '|IKJoints|IKParent.shearYZ'), graph.outputs)
        self.assertEqual(decode_source_body_matrix(canonical(asdict(graph)), allow_decompose_outputs=True), graph)
        with self.assertRaises(CharacterRegistryError):
            decode_source_body_matrix(canonical(asdict(graph)))

    def test_opm_retains_single_matrix_output(self):
        graph = plan_graph('|IKJoints|IKParent', '|IKJoints', '|Body|Scapula_L', 4, True)
        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(graph.outputs, (('IKParentPM.outputMatrix', '|IKJoints|IKParent.offsetParentMatrix'),))
        self.assertEqual(decode_source_body_matrix(canonical(asdict(graph))), graph)

    def test_decomposition_cannot_write_an_unrelated_target(self):
        graph = asdict(plan_graph('|IKJoints|IKParent', '|IKJoints', '|Body|Scapula_L', 4, False))
        graph['outputs'] = ((*graph['outputs'][:-1], ('IKParentDM.outputShearZ', '|Foreign.shearYZ')))
        with self.assertRaises(CharacterRegistryError):
            decode_source_body_matrix(canonical(graph), allow_decompose_outputs=True)
