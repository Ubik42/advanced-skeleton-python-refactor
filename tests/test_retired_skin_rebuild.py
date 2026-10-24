"""Native deleted influence caches survive rebuild without reconnecting."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from adv_py.core.character_body_retirement import (
    RetiredBodyInput,CharacterRetiredBodyJoint,retire_body_correspondence)
from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.character_preservation import validate_preservation
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.adapters.maya_body_retirement_rebuild import _retained_inputs,_native_delete_addresses
from adv_py.adapters.maya_character_body_retirement import cached_skin_matrix
import test_character_preservation as preservation_fixtures


class RetiredSkinRebuildTests(unittest.TestCase):
    def test_retirement_rebuild_keeps_native_short_addresses_and_order(self):
        class Commands:
            def listRelatives(self,node,**flags):
                self.query=(node,flags)
                return ['TipB','Middle','TipA']
            def ls(self,node,**flags):
                return ['|Root|'+node]
        commands=Commands()
        self.assertEqual(_native_delete_addresses(SimpleNamespace(_cmds=commands),
            ('|Root|TipA','|Root|TipB')),('TipB','TipA'))
        self.assertEqual(commands.query,('DeformationSystem',dict(allDescendents=True,type='joint')))
        with self.assertRaises(CharacterRegistryError):
            _native_delete_addresses(SimpleNamespace(_cmds=commands),('|Root|Unknown',))

    def fixture(self):
        case=preservation_fixtures.CharacterPreservationTests()
        case.setUp()
        snapshot=case.snapshot
        before=snapshot.registration
        tip=before.body[-1]
        node=next(row for row in before.nodes if row.path==tip.path)
        item=RetiredBodyInput(tip.path+'.worldMatrix[0]','skin.matrix[4]',
            'skin-id','matrix',tip.matrix,'initial-deleted-id')
        retired=CharacterRetiredBodyJoint(tip.path,node.uuid,tip.parent,tip.matrix,0,
            len(before.body)-1,(item,))
        registration=retire_body_correspondence(before,(retired,),
            tuple(row for row in before.nodes if row.path!=tip.path),before.channels)
        skin=replace(snapshot.skins[0],influences=((4,'',tip.matrix,''),),
            cached_matrices=((4,tip.matrix,'initial-deleted-id'),))
        snapshot=replace(snapshot,registration=registration,skins=(skin,))
        return snapshot,retired,item

    def test_snapshot_requires_actual_retirement_not_just_an_empty_source(self):
        snapshot,retired,item=self.fixture()
        self.assertEqual(validate_preservation(snapshot),snapshot)
        skin=snapshot.skins[0]
        for invalid in (replace(skin,cached_matrices=()),
            replace(skin,cached_matrices=((7,item.value,item.source_uuid),)),
            replace(skin,cached_matrices=((4,item.value,'new-stage-tip-id'),)),
            replace(skin,cached_matrices=skin.cached_matrices*2),
            replace(skin,influences=((4,'newTip.worldMatrix[0]',item.value,''),))):
            with self.subTest(skin=invalid),self.assertRaises(CharacterRegistryError):
                validate_preservation(replace(snapshot,skins=(invalid,)))

    def commands(self,item):
        class Commands:
            origin_live=False
            changed=False
            connected=False
            def ls(self,address,**flags):
                if address=='skin-id':return ['model:skin']
                if address=='model:skin' and flags.get('uuid'):return ['skin-id']
                if address==item.source_uuid and self.origin_live:return ['other:resurrected']
                return []
            def objExists(self,plug):return plug=='model:skin.matrix[4]'
            def attributeQuery(self,name,**flags):return 'matrix'
            def getAttr(self,plug,**flags):
                if flags.get('multiIndices'):return [4]
                if flags.get('type'):return 'matrix'
                matrix=list(item.value)
                if self.changed:matrix[12]+=1.
                return [tuple(matrix)]
            def connectionInfo(self,plug,**flags):
                return 'newTip.worldMatrix[0]' if self.connected else ''
            def listConnections(self,*args,**flags):return []
        return Commands()

    def test_foreign_skin_carries_exact_uuid_value_and_old_origin(self):
        snapshot,retired,item=self.fixture()
        raw=self.commands(item)
        host=SimpleNamespace(_cmds=SimpleNamespace(raw=raw,identity=CharacterIdentity('stage')))
        result=_retained_inputs(host,retired,set(),snapshot)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0],replace(item,destination='model:skin.matrix[4]'))
        for flag in ('changed','connected','origin_live'):
            setattr(raw,flag,True)
            with self.subTest(flag=flag),self.assertRaises(CharacterRegistryError):
                _retained_inputs(host,retired,set(),snapshot)
            setattr(raw,flag,False)

    def test_unretained_cached_target_cannot_be_silently_dropped_or_adopted(self):
        snapshot,retired,item=self.fixture()
        host=SimpleNamespace(_cmds=self.commands(item))
        with self.assertRaisesRegex(CharacterRegistryError,'保留快照'):
            _retained_inputs(host,retired,set(),None)
        with self.assertRaisesRegex(CharacterRegistryError,'保留对象'):
            _retained_inputs(host,retired,set(),replace(snapshot,skins=()))
        self.assertEqual(_retained_inputs(host,retired,{(item.source,item.destination)},None),())

    def test_cache_lookup_uses_skin_uuid_and_slot_not_a_stale_namespace(self):
        snapshot,retired,item=self.fixture()
        raw=self.commands(item)
        # The saved document still names the old local skin; the retained
        # object is currently addressed through its actual model namespace.
        raw.objExists=lambda plug:plug in ('skin.matrix[4]','model:skin.matrix[4]')
        def ls(address,**flags):
            if address in ('skin','model:skin') and flags.get('uuid'):return ['skin-id']
            if address=='skin-id':return ['model:skin']
            return []
        raw.ls=ls
        host=SimpleNamespace(_cmds=raw)
        self.assertEqual(cached_skin_matrix(host,'model:skin',4,
            registration=snapshot.registration),(item.value,item.source_uuid))
        self.assertIsNone(cached_skin_matrix(host,'model:skin',7,registration=snapshot.registration))

    def test_absent_skin_element_is_never_read_as_a_cached_influence(self):
        snapshot,retired,item=self.fixture()
        absent=replace(item,value=None,element_exists=False)
        registration=replace(snapshot.registration,retired_body=(
            replace(retired,frozen_inputs=(absent,)),))
        raw=self.commands(absent)
        reads=[]
        def get_attr(plug,**flags):
            reads.append(plug)
            if plug=='model:skin.matrix' and flags.get('multiIndices'):
                return []
            raise AssertionError('An absent sparse element was queried: '+plug)
        raw.getAttr=get_attr
        host=SimpleNamespace(_cmds=raw)
        self.assertIsNone(cached_skin_matrix(host,'model:skin',4,registration=registration))
        self.assertEqual(reads,['model:skin.matrix'])


if __name__=='__main__':unittest.main()
