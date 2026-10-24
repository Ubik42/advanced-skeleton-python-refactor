"""Export deletion preserves identity without silently shortening solvers."""
from dataclasses import replace, asdict
import json
from types import SimpleNamespace
import unittest

from adv_py.core.character_registry import (
    CharacterRegistryError, encode_registration, decode_registration, digest,
)
from adv_py.core.character_body_retirement import (
    CharacterRetiredBodyJoint, RetiredBodyInput, complete_body_bindings,
    RetiredBodyGraphNode,retire_body_correspondence,
)
from adv_py.adapters.maya_character_body_retirement import audit
from adv_py.adapters.maya_character_body_retirement import (
    source_record,source_property,is_connected_or_retired,removed_graph_node,validation)
from test_character_registry import registration_fixture


class BodyRetirementTests(unittest.TestCase):
    def fixture(self, frozen=()):
        registration = registration_fixture()
        tip = registration.body[-1]
        node = next(node for node in registration.nodes if node.path==tip.path)
        retired = CharacterRetiredBodyJoint(tip.path,node.uuid,tip.parent,tip.matrix,0,
                                            len(registration.body)-1,tuple(frozen))
        after = retire_body_correspondence(registration,(retired,),
            tuple(row for row in registration.nodes if row.path!=tip.path),registration.channels)
        return registration,after,retired

    def test_legacy_registration_document_stays_version_one(self):
        document = json.loads(encode_registration(registration_fixture()))
        self.assertEqual(document['version'],1)
        self.assertNotIn('retired_body',document['payload'])

    def test_rebuilt_cache_preserves_the_actual_historical_origin(self):
        tip = registration_fixture().body[-1]
        frozen = RetiredBodyInput(tip.path+'.worldMatrix[0]','model:skin.matrix[7]',
            'skin-id','matrix',tip.matrix,'first-deleted-tip-id')
        _,after,retired = self.fixture((frozen,))
        text=encode_registration(after)
        self.assertEqual(json.loads(text)['version'],9)
        self.assertEqual(decode_registration(text),after)
        from adv_py.core.character_body_retirement import frozen_origin
        self.assertEqual(frozen_origin(retired,frozen),'first-deleted-tip-id')
        self.assertNotEqual(frozen_origin(retired,frozen),retired.uuid)
        invalid=replace(frozen,source_uuid=after.nodes[0].uuid)
        with self.assertRaisesRegex(CharacterRegistryError,'历史来源'):
            encode_registration(replace(after,retired_body=(replace(retired,frozen_inputs=(invalid,)),)))

    def test_native_pose_cleanup_removes_only_observed_deleted_targets(self):
        tip=registration_fixture().body[-1]
        pose=RetiredBodyInput(tip.path+'.worldMatrix[0]','bindPose.worldMatrix[7]',
            'old-pose-id','matrix',tip.matrix)
        skin=replace(pose,destination='skin.matrix[7]',destination_uuid='skin-id')
        before,after,retired=self.fixture((pose,skin))
        from adv_py.core.character_body_retirement import forget_deleted_retirement_inputs
        updated=forget_deleted_retirement_inputs(after,('old-pose-id',))
        self.assertEqual(updated.retired_body[0].frozen_inputs,(skin,))
        self.assertEqual(complete_body_bindings(updated),before.body)
        self.assertEqual(updated.spine,before.spine)
        self.assertEqual(updated.compatibility_digest,after.compatibility_digest)
        self.assertEqual(decode_registration(encode_registration(updated)),updated)
        with self.assertRaisesRegex(CharacterRegistryError,'存活节点'):
            forget_deleted_retirement_inputs(after,(after.nodes[0].uuid,))

    def test_roundtrip_keeps_all_controls_spine_and_bind_compatibility(self):
        before,after,retired = self.fixture()
        self.assertEqual(len(after.body),len(before.body)-1)
        self.assertEqual(after.channels,before.channels)
        self.assertEqual(after.spine,before.spine)
        self.assertEqual(complete_body_bindings(after),before.body)
        self.assertEqual(after.compatibility_digest,before.compatibility_digest)
        self.assertEqual(decode_registration(encode_registration(after)),after)
        self.assertEqual(json.loads(encode_registration(after))['version'],8)
        self.assertNotIn(retired.path,{node.path for node in after.nodes})

    def test_part_reparent_updates_retired_parent_and_embedded_source_records(self):
        from adv_py.core.fit_part import FitPartFinalPaths, rebase_plan_paths_after_parts
        _,_,tip=self.fixture()
        constraint=RetiredBodyGraphNode(tip.path+'|TipOrient','constraint-id','orientConstraint',
            ((tip.parent+'.worldMatrix[0]',tip.path+'|TipOrient.targetMatrix'),))
        frozen=RetiredBodyInput(tip.path+'.worldMatrix[0]','skin.matrix[7]',
            'skin-id','matrix',tip.matrix,'historical-tip-id')
        record=dict(body=tip.path,parent=tip.parent,matrix=tip.matrix,uuid='historical-tip-id')
        tip=replace(tip,removed_nodes=(constraint,),frozen_inputs=(frozen,),
            records=(('advPySourceEndMatrix',json.dumps(record)),))
        part=tip.parent+'|InsertedPart'
        new_tip=part+'|'+tip.path.rsplit('|',1)[-1]
        paths=FitPartFinalPaths((),(),((tip.path,new_tip),(tip.parent,tip.parent)))
        updated=rebase_plan_paths_after_parts(tip,paths)
        self.assertEqual(updated.path,new_tip)
        self.assertEqual(updated.parent,part)
        self.assertEqual(updated.uuid,tip.uuid)
        self.assertEqual(updated.matrix,tip.matrix)
        self.assertEqual(updated.frozen_inputs[0].source,new_tip+'.worldMatrix[0]')
        self.assertEqual(updated.frozen_inputs[0].source_uuid,'historical-tip-id')
        self.assertEqual(updated.removed_nodes[0].path,new_tip+'|TipOrient')
        self.assertEqual(updated.removed_nodes[0].uuid,'constraint-id')
        self.assertEqual(updated.removed_nodes[0].inputs[0][1],new_tip+'|TipOrient.targetMatrix')
        stored=json.loads(updated.records[0][1])
        self.assertEqual(stored['body'],new_tip)
        self.assertEqual(stored['uuid'],'historical-tip-id')
        self.assertEqual(tuple(stored['matrix']),tip.matrix)

    def test_rejects_unrecorded_deletion_or_replacement_identity(self):
        before,after,retired = self.fixture()
        for invalid in (replace(retired,uuid='replacement'),
                        replace(retired,body_index=0),
                        replace(retired,parent=before.body[0].path)):
            with self.assertRaises(CharacterRegistryError):
                retire_body_correspondence(before,(invalid,),after.nodes,before.channels)
        with self.assertRaises(CharacterRegistryError):
            retire_body_correspondence(before,(retired,),before.nodes,before.channels)

    def test_rejects_retired_parent_with_live_descendant(self):
        before = registration_fixture()
        joint = before.body[-2]
        node = next(row for row in before.nodes if row.path==joint.path)
        retired = CharacterRetiredBodyJoint(joint.path,node.uuid,joint.parent,joint.matrix,0,28)
        with self.assertRaisesRegex(CharacterRegistryError,'子关节'):
            retire_body_correspondence(before,(retired,),
                tuple(row for row in before.nodes if row.path!=joint.path),before.channels)

    def test_frozen_inputs_are_exact_typed_values_and_reject_foreign_sources(self):
        tip = registration_fixture().body[-1]
        frozen = RetiredBodyInput(tip.path+'.worldMatrix[0]','cached.matrixIn[0]',
                                  'cached-id','matrix',tip.matrix)
        _,after,_ = self.fixture((frozen,))
        self.assertEqual(decode_registration(encode_registration(after)),after)
        original = json.loads(encode_registration(after))
        for key,value in (('source','other.worldMatrix[0]'),('datatype','string'),
                          ('value',[1.,2.]),('destination_uuid','')):
            document = json.loads(json.dumps(original))
            document['payload']['retired_body'][0]['frozen_inputs'][0][key]=value
            document['digest']=digest(document['payload'])
            with self.assertRaises(CharacterRegistryError):
                decode_registration(json.dumps(document))

    def test_audit_rejects_same_name_replacement_and_changed_cached_value(self):
        tip = registration_fixture().body[-1]
        frozen = RetiredBodyInput(tip.path+'.scaleX','cached.input1X','cached-id','double',(1.,))
        _,registration,_ = self.fixture((frozen,))
        class Commands:
            replacement = False
            value = 1.
            def objExists(self,path):return path=='cached.input1X' or self.replacement and path==tip.path
            def ls(self,path,**kwargs):
                if path=='cached' and kwargs.get('uuid'):return ['cached-id']
                if path=='cached-id':return ['cached']
                return []
            def getAttr(self,plug,**kwargs):return 'double' if kwargs.get('type') else self.value
            def attributeQuery(self,name,**kwargs):return 'double'
            def connectionInfo(self,plug,**kwargs):return ''
        commands = Commands()
        host = SimpleNamespace(_cmds=commands)
        audit(host,registration)
        commands.value=2.
        with self.assertRaisesRegex(CharacterRegistryError,'值变化'):audit(host,registration)
        commands.value=1.
        commands.replacement=True
        with self.assertRaisesRegex(CharacterRegistryError,'重新出现'):audit(host,registration)

    def test_removed_attached_graph_roundtrip_keeps_exact_edges_and_source_flags(self):
        before,after,retired=self.fixture()
        constraint=RetiredBodyGraphNode(retired.path+'|TipOrient','tip-orient-id','orientConstraint',
            (('reverse.outputX',retired.path+'|TipOrient.w0'),))
        incoming=((constraint.path+'.constraintRotateX',retired.path+'.rotateX'),)
        retired=replace(retired,removed_nodes=(constraint,),incoming=incoming,
            properties=(('segmentScaleCompensate',False),('advPySourceFkPoint',True)),
            records=(('advPySourceEndMatrix',json.dumps(dict(body=retired.path,matrix=retired.matrix))),))
        after=retire_body_correspondence(before,(retired,),after.nodes,after.channels)
        self.assertEqual(decode_registration(encode_registration(after)),after)
        class Commands:
            collision=False
            def objExists(self,address):return self.collision and address=='TipOrient'
            def ls(self,*args,**flags):return []
        host=SimpleNamespace(_cmds=Commands(),scene_address=lambda value:value)
        with validation(host,after):
            self.assertEqual(removed_graph_node(host,'TipOrient'),constraint)
            self.assertTrue(is_connected_or_retired(host,'reverse.outputX','TipOrient.w0'))
            self.assertTrue(is_connected_or_retired(host,'TipOrient.constraintRotateX',retired.path+'.rotateX'))
            self.assertTrue(is_connected_or_retired(host,'TipOrient.constraintRotate.constraintRotateX',
                retired.path+'.rotate.rotateX'))
            self.assertFalse(is_connected_or_retired(host,'reverse.outputY','TipOrient.w0'))
            self.assertFalse(source_property(host,retired.path,'segmentScaleCompensate'))
            self.assertTrue(source_property(host,retired.path,'advPySourceFkPoint'))
            self.assertEqual(source_record(host,retired.path,'advPySourceEndMatrix'),retired.records[0][1])
            host._cmds.collision=True
            self.assertIsNone(removed_graph_node(host,'TipOrient'))

    def test_source_settings_and_archived_constraint_identities_are_closed(self):
        before,after,retired=self.fixture()
        wrong_properties=((('unknown',True),),(('segmentScaleCompensate',1),),
                          (('segmentScaleCompensate',True),('segmentScaleCompensate',False)))
        for properties in wrong_properties:
            with self.subTest(properties=properties),self.assertRaises(CharacterRegistryError):
                retire_body_correspondence(before,(replace(retired,properties=properties),),after.nodes,after.channels)
        node=RetiredBodyGraphNode(retired.path+'|TipConstraint',retired.uuid,'orientConstraint')
        with self.assertRaises(CharacterRegistryError):
            retire_body_correspondence(before,(replace(retired,removed_nodes=(node,)),),after.nodes,after.channels)
        node=replace(node,uuid='child-id',node_type='expression')
        with self.assertRaises(CharacterRegistryError):
            retire_body_correspondence(before,(replace(retired,removed_nodes=(node,)),),after.nodes,after.channels)
        # A direct FK matrix needs its captured translation policy; otherwise
        # rebuild would have to invent a feature that no source record proves.
        retired=replace(retired,records=(('advPySourceFkMatrix','{}'),))
        with self.assertRaisesRegex(CharacterRegistryError,'位置接收'):
            retire_body_correspondence(before,(retired,),after.nodes,after.channels)


if __name__=='__main__':unittest.main()
