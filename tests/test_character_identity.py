import unittest
from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.character_registry import CharacterRegistryError


class CharacterIdentityTests(unittest.TestCase):
    def test_nested_namespace_addresses_preserve_plugs_and_components(self):
        identity=CharacterIdentity('shot:hero')
        for local,physical in (
            ('AdvPy_CharacterRegistry','shot:hero:AdvPy_CharacterRegistry'),
            ('|Root_M|Hip_R.rotateX','|shot:hero:Root_M|shot:hero:Hip_R.rotateX'),
            ('mesh.vtx[4:8]','shot:hero:mesh.vtx[4:8]'),
        ):
            self.assertEqual(identity.to_scene(local),physical)
            self.assertEqual(identity.to_local(physical),local)
            self.assertTrue(identity.owns(physical))
        self.assertEqual(identity.to_local('other:Root_M'),'other:Root_M')
        self.assertEqual(identity.to_scene(identity.to_local('|Root_M')),'|:Root_M')
        self.assertFalse(identity.owns('|other:Group|shot:hero:Root_M'))

    def test_identity_validation_and_root_scope(self):
        for bad in ('hero:','hero::rig',':hero','hero*','hero|rig','hero.node',None):
            with self.assertRaises(CharacterRegistryError):CharacterIdentity(bad)
        root=CharacterIdentity('')
        self.assertEqual(root.registry_path,'AdvPy_CharacterRegistry')
        self.assertTrue(root.owns('|Root_M|Hip_R'))
        self.assertFalse(root.owns('|hero:Root_M'))

    def test_command_boundary_preserves_data_and_rejects_foreign_writes(self):
        from adv_py.adapters.maya_namespace import MayaCharacterCommands
        class Commands:
            def __init__(self):self.calls=[]
            def namespace(self,**kwargs):return False if kwargs.get('query') else True
            def setAttr(self,*args,**kwargs):self.calls.append((args,kwargs))
            def getAttr(self,*args,**kwargs):self.calls.append((args,kwargs));return 'partner:unchanged-data'
        raw=Commands();commands=MayaCharacterCommands(raw,'hero')
        document='{"path":"|Root_M","name":"partner:payload"}'
        commands.setAttr('AdvPy_CharacterRegistry.document',document,type='string')
        self.assertEqual(raw.calls[-1],((':hero:AdvPy_CharacterRegistry.document',document),{'type':'string'}))
        before=len(raw.calls)
        with self.assertRaises(CharacterRegistryError):commands.setAttr('partner:Control.rotateX',10.)
        self.assertEqual(len(raw.calls),before)
        self.assertEqual(commands.getAttr('partner:Control.label'),'partner:unchanged-data')
