"""Connected MoCap must retain actual helpers while receiver UUIDs change."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.character_registry import CharacterRegistryError, canonical
from adv_py.core.source_name_matcher_session import (
    ATTRIBUTE, decode_session, encode_session, rebase_session)
from adv_py.adapters.maya_source_name_matcher_session import remember, audit
from adv_py.adapters.maya_source_mocap_rebuild import (
    capture, retained_nodes, install, verify)
from test_source_name_matcher_session import SessionCommands


class SourceMocapRebuildTests(unittest.TestCase):
    def fixture(self):
        c = SessionCommands()
        host = SimpleNamespace(_cmds=c,_require_transaction=lambda:None,
            scene_address=lambda name:c.group if name=='MoCapConstraints' else name)
        value = remember(host,((c.control,None,c.constraint),))
        return host,c,value

    def moved(self,animated=False):
        host,c,value = self.fixture()
        original = SimpleNamespace(mocap_session=encode_session(value),curves=())
        ownership = SimpleNamespace(nodes=(
            ('control','control-id','new-control-id','transform'),
            ('controls','controls-id','new-controls-id','transform')),
            removed_nodes=())
        staged = SimpleNamespace(original=original,ownership=ownership)
        parent = '|stage:controls'
        control = parent+'|stage:FK'
        constraint = control+'|FK_orientConstraint1'
        c.nodes[parent] = ('new-controls-id','transform',None)
        c.nodes[control] = ('new-control-id','transform',parent)
        c.nodes.pop(c.constraint)
        c.nodes[constraint] = ('constraint-id','orientConstraint',control)
        def move(plug):
            node,attribute=plug.split('.',1)
            return {c.constraint:constraint,c.control:control}.get(node,node)+'.'+attribute
        c.inputs = {move(target):move(source) for target,source in c.inputs.items()}
        return host,c,value,staged,control,constraint

    def test_capture_retains_exact_helper_objects_and_locked_document(self):
        host,c,value = self.fixture()
        self.assertEqual(decode_session(capture(host)),value)
        self.assertEqual(set(retained_nodes(host,encode_session(value))),{c.group,c.constraint})
        c.nodes[c.target] = ('replacement-target','joint','|external')
        with self.assertRaises(CharacterRegistryError):capture(host)

    def test_uuid_rebase_preserves_external_target_and_native_constraint(self):
        _,c,value = self.fixture()
        changed = rebase_session(value,{
            'control-id':('|stage:controls|stage:FK','new-control'),
            'constraint-id':('|stage:controls|stage:FK|FK_orientConstraint1','constraint-id')})
        self.assertEqual(changed['receivers'][0]['uuid'],'new-control')
        row = next(node for node in changed['nodes'] if node['uuid']=='constraint-id')
        self.assertEqual(row['parent'],'new-control')
        target = next(edge for edge in row['inputs'] if edge['source_uuid']=='target-id')
        self.assertEqual(target['source'],c.target+'.worldMatrix[0]')
        self.assertEqual(value['receivers'][0]['uuid'],'control-id')
        with self.assertRaisesRegex(CharacterRegistryError,'不能替换'):
            rebase_session(value,{'constraint-id':(c.constraint,'replacement-constraint')})

    def test_install_records_actual_staged_graph_without_recreating_helpers(self):
        host,c,value,staged,control,constraint = self.moved()
        before = deepcopy(c.nodes),deepcopy(c.inputs)
        install(host,staged)
        self.assertEqual((c.nodes,c.inputs),before)
        saved = decode_session(c.attrs[c.group+'.'+ATTRIBUTE])
        self.assertEqual(saved['receivers'][0]['path'],control)
        self.assertEqual(saved['receivers'][0]['uuid'],'new-control-id')
        self.assertEqual(saved['nodes'][0]['uuid'],'constraint-id')
        self.assertEqual(saved['nodes'][0]['path'],constraint)
        self.assertEqual(len(audit(host)),3)
        verify(host,staged)

    def test_install_cannot_bless_a_changed_external_target_or_helper_uuid(self):
        host,c,_,staged,control,constraint = self.moved()
        c.inputs[constraint+'.target[0].targetParentMatrix']=control+'.worldMatrix[0]'
        with self.assertRaisesRegex(CharacterRegistryError,'实际交接图'):
            install(host,staged)
        host,c,_,staged,_,constraint = self.moved()
        c.nodes[constraint] = ('replacement-constraint','orientConstraint',c.nodes[constraint][2])
        with self.assertRaisesRegex(CharacterRegistryError,'UUID 缺失'):
            install(host,staged)

    def test_removing_connected_spline_receiver_cannot_silently_detach_session(self):
        host,c,_,staged,_,_ = self.moved()
        staged.ownership.removed_nodes=(('control','control-id','transform'),)
        with self.assertRaisesRegex(CharacterRegistryError,'正在动捕连接'):
            install(host,staged)

    def test_compound_channel_spelling_is_canonical_on_capture(self):
        host,c,_ = self.fixture()
        for axis in 'XYZ':
            c.inputs[c.control+'.rotate'+axis]=c.constraint+'.constraintRotate.constraintRotate'+axis
        value=remember(host,((c.control,None,c.constraint),))
        self.assertEqual(value['receivers'][0]['inputs'][0]['source'],c.constraint+'.constraintRotateX')
        self.assertEqual(len(audit(host)),3)


if __name__=='__main__':unittest.main()
