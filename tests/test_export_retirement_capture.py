"""Native DAG-set membership is not a frozen numeric export input."""
from types import SimpleNamespace
from dataclasses import asdict
import unittest

from adv_py.adapters.maya_character_body_retirement import capture,finish
from adv_py.adapters.maya_original_export_preparation import MayaOriginalExportPreparationHost
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.character_body_retirement import decode_retired_body


class ExportRetirementCaptureTests(unittest.TestCase):
    def fixture(self):
        tip='|Body|Tip'
        matrix=tuple(float(i%5==0) for i in range(16))
        class Commands:
            deleted=False
            def ls(self,name,**flags):
                if name==tip:return [] if self.deleted else ['tip-id'] if flags.get('uuid') else [tip]
                if name=='tip-id':return [] if self.deleted else [tip]
                if name=='skin':return ['skin-id'] if flags.get('uuid') else ['skin']
                if name=='skin-id':return ['skin']
                return []
            def objExists(self,name):
                return name in ('skin.matrix[3]',) or name==tip and not self.deleted
            def getAttr(self,plug,**flags):
                if flags.get('multiIndices'):return [3] if plug=='skin.matrix' else []
                if plug=='skin.matrix[3]':return 'matrix' if flags.get('type') else [matrix]
                if plug.endswith('.rotateOrder'):return 0
                if plug.endswith('.segmentScaleCompensate'):return True
                raise AssertionError(plug)
            def nodeType(self,node):return 'objectSet' if node=='AllSet' else 'skinCluster'
            def attributeQuery(self,name,**flags):return {'lockWeights':'bool','influenceColor':'float3'}.get(name) or self.getAttr('skin.matrix[3]',type=True)
            def listRelatives(self,*args,**flags):return []
            def listConnections(self,*args,**flags):
                if flags.get('destination'):
                    return [tip+'.instObjGroups','AllSet.dagSetMembers[5]',
                            tip+'.worldMatrix[0]','skin.matrix[3]',
                            tip+'.lockInfluenceWeights','skin.lockWeights[3]',
                            tip+'.objectColorRGB','skin.influenceColor[3]']
                return []
            def connectionInfo(self,*args,**flags):return ''
        commands=Commands()
        host=SimpleNamespace(_cmds=commands,_resolve_connected_node=lambda name:name,scene_address=lambda name:name,
                             _original_game_scaling_validation=((),SimpleNamespace(joints=())))
        registration=SimpleNamespace(body=(SimpleNamespace(path=tip,parent='|Body',matrix=matrix),),
            retired_body=(),nodes=(SimpleNamespace(path=tip,uuid='tip-id'),),body_root='|Body')
        return host,registration,commands,tip

    def test_member_deletion_keeps_only_actual_skin_matrix_cache(self):
        host,registration,commands,tip=self.fixture()
        rows=capture(host,registration,(tip,))
        self.assertEqual(rows[0].outgoing[0],(tip+'.worldMatrix[0]','skin.matrix[3]','skin-id'))
        commands.deleted=True
        retired=finish(host,rows)
        self.assertEqual(retired[0].frozen_inputs[0].datatype,'matrix')
        self.assertEqual(retired[0].frozen_inputs[0].value,registration.body[0].matrix)
        self.assertTrue(all(not item.element_exists and item.value is None
                            for item in retired[0].frozen_inputs[1:]))

    def test_empty_numeric_cache_is_rejected_with_actual_destination(self):
        host,registration,commands,tip=self.fixture()
        rows=capture(host,registration,(tip,))
        original=commands.getAttr
        commands.getAttr=lambda plug,**flags: ([3] if plug=='skin.matrix' else []) if flags.get('multiIndices') else 'double' if flags.get('type') else None
        commands.deleted=True
        with self.assertRaisesRegex(CharacterRegistryError,r'skin.matrix\[3\]'):
            finish(host,rows)

    def test_native_typed_empty_matrix_remains_absent(self):
        host,registration,commands,tip=self.fixture()
        rows=capture(host,registration,(tip,))
        commands.getAttr=lambda plug,**flags: ([3] if plug=='skin.matrix' else []) if flags.get('multiIndices') else 'matrix' if flags.get('type') else None
        commands.deleted=True
        self.assertIsNone(finish(host,rows)[0].frozen_inputs[0].value)

    def test_deleted_matrix_element_is_not_materialized_by_reading(self):
        host,registration,commands,tip=self.fixture()
        rows=capture(host,registration,(tip,))
        original=commands.getAttr
        def read(plug,**flags):
            if flags.get('multiIndices'):return []
            if plug=='skin.matrix[3]':raise AssertionError('deleted element must not be read')
            return original(plug,**flags)
        commands.getAttr=read
        commands.attributeQuery=lambda name,**flags: {'matrix':'matrix','lockWeights':'bool','influenceColor':'float3'}[name]
        commands.deleted=True
        item=finish(host,rows)[0].frozen_inputs[0]
        self.assertFalse(item.element_exists)
        self.assertIsNone(item.value)

    def test_removed_skin_index_keeps_native_orphan_weights_without_new_influence(self):
        import test_retired_skin_rebuild as skin_tests
        from dataclasses import replace
        from adv_py.core.character_preservation import validate_preservation
        from adv_py.core.character_registry import encode_registration,decode_registration
        snapshot,row,item=skin_tests.RetiredSkinRebuildTests().fixture()
        index=snapshot.skins[0].influences[0][0]
        self.assertEqual(index,4)
        item=replace(item,value=None,element_exists=False)
        row=replace(row,frozen_inputs=(item,))
        registration=replace(snapshot.registration,retired_body=(row,))
        skin=replace(snapshot.skins[0],influences=((1,'Root.worldMatrix[0]',row.matrix,''),),
                     cached_matrices=(),influence_locks=(),weights=((0,((4,.35),(1,.65))),))
        updated=replace(snapshot,registration=registration,skins=(skin,))
        self.assertEqual(validate_preservation(updated),updated)
        text=encode_registration(registration)
        import json
        self.assertEqual(json.loads(text)['version'],10)
        self.assertEqual(decode_registration(text),registration)
        with self.assertRaises(CharacterRegistryError):
            validate_preservation(replace(updated,registration=replace(registration,retired_body=())))

    def test_empty_skin_matrix_has_serialized_deleted_origin(self):
        import test_retired_skin_rebuild as skin_tests
        from dataclasses import replace
        from adv_py.core.character_preservation import validate_preservation
        from adv_py.core.character_registry import encode_registration,decode_registration
        snapshot,row,item=skin_tests.RetiredSkinRebuildTests().fixture()
        row=replace(row,frozen_inputs=(replace(item,value=None),))
        registration=replace(snapshot.registration,retired_body=(row,))
        skin=replace(snapshot.skins[0],cached_matrices=((4,None,item.source_uuid),))
        updated=replace(snapshot,registration=registration,skins=(skin,))
        self.assertEqual(validate_preservation(updated),updated)
        self.assertEqual(decode_registration(encode_registration(registration)),registration)

    def test_export_host_resolves_using_its_scoped_commands(self):
        seen=[]
        host=object.__new__(MayaOriginalExportPreparationHost)
        host._cmds=SimpleNamespace(ls=lambda name,**flags: seen.append((name,flags)) or ['|Rig|DeformationSystem'])
        self.assertEqual(host._unique('DeformationSystem','transform'),'|Rig|DeformationSystem')
        self.assertEqual(seen,[('DeformationSystem',dict(long=True,type='transform'))])
        host._cmds=SimpleNamespace(ls=lambda *args,**flags: [])
        with self.assertRaises(ValueError):host._unique('DeformationSystem','transform')

    def test_observed_external_spline_space_deletion_has_closed_provenance(self):
        host,registration,commands,tip=self.fixture()
        space='|Motion|SplineChestSpace'
        registration.spine=SimpleNamespace(body_joints=(tip,),chest_space=space)
        registration.nodes+= (SimpleNamespace(path=space,uuid='space-id'),)
        old_ls,old_exists,old_kind,old_connections=commands.ls,commands.objExists,commands.nodeType,commands.listConnections
        commands.ls=lambda name,**flags: (['space-id'] if flags.get('uuid') else [space]) if name==space else (
            [] if commands.deleted else [space]) if name=='space-id' else old_ls(name,**flags)
        commands.objExists=lambda name: not commands.deleted if name==space else old_exists(name)
        commands.nodeType=lambda name: 'transform' if name==space else old_kind(name)
        commands.listConnections=lambda name,**flags: [] if name==space else old_connections(name,**flags)
        rows=capture(host,registration,(tip,))
        self.assertEqual(rows[0].removed_nodes[0].path,space)
        commands.deleted=True
        retired=finish(host,rows)[0]
        self.assertEqual(retired.removed_nodes[0].uuid,'space-id')
        raw=[asdict(retired)]
        live=(SimpleNamespace(path='|Body',uuid='body-id'),)
        self.assertEqual(decode_retired_body(raw,'|Body',(),live,historical_origins=True,array_presence=True,
            external_spline_spaces={tip:{space}}),(retired,))
        with self.assertRaises(CharacterRegistryError):
            decode_retired_body(raw,'|Body',(),live,historical_origins=True,array_presence=True)

    def test_native_surviving_spline_space_is_not_declared_deleted(self):
        host,registration,commands,tip=self.fixture()
        space='|Motion|SplineChestSpace'
        registration.spine=SimpleNamespace(body_joints=(tip,),chest_space=space)
        registration.nodes+= (SimpleNamespace(path=space,uuid='space-id'),)
        old_ls,old_exists,old_kind,old_connections=commands.ls,commands.objExists,commands.nodeType,commands.listConnections
        commands.ls=lambda name,**flags: ['space-id'] if name==space and flags.get('uuid') else (
            [space] if name in (space,'space-id') else old_ls(name,**flags))
        commands.objExists=lambda name: name==space or old_exists(name)
        commands.nodeType=lambda name: 'transform' if name==space else old_kind(name)
        commands.listConnections=lambda name,**flags: [] if name==space else old_connections(name,**flags)
        rows=capture(host,registration,(tip,))
        commands.deleted=True
        self.assertEqual(finish(host,rows)[0].removed_nodes,())


if __name__=='__main__':
    unittest.main()
