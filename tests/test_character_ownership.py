import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from adv_py.adapters.maya_character_ownership import _graph,_missing_fit_fat_connection


class CharacterOwnershipTests(unittest.TestCase):
    def graph(self,conversion,shared=False):
        edges=(('driver.output',conversion+'.input'),(conversion+'.output','joint.rotateX'))
        if shared:edges+=((conversion+'.output','foreign.input'),)
        commands=Mock()
        commands.nodeType.return_value='unitConversion'
        with patch('adv_py.adapters.maya_character_ownership.connections',side_effect=lambda host,node:tuple(
                edge for edge in edges if any(p.split('.',1)[0]==node for p in edge))):
            return _graph(SimpleNamespace(_cmds=commands),('driver','joint'))

    def test_implicit_conversion_identity_comes_from_edges_not_global_numbering(self):
        old,old_edges=self.graph(':unitConversion1')
        new,new_edges=self.graph(':unitConversion63')
        self.assertEqual(set(old),set(new))
        self.assertEqual(old_edges,new_edges)
        self.assertEqual(len(old),3)

    def test_shared_conversion_is_never_claimed_for_cleanup(self):
        nodes,edges=self.graph(':unitConversion1',shared=True)
        self.assertEqual(set(nodes),{'driver','joint'})
        self.assertIn(('driver.output',':unitConversion1.input'),edges)

    def test_only_unconnected_original_fit_fat_receiver_can_be_repaired(self):
        commands=Mock()
        commands.objExists.return_value=True
        commands.nodeType.return_value='multiplyDivide'
        commands.getAttr.return_value=1
        commands.connectionInfo.return_value=''
        host=SimpleNamespace(_cmds=commands)
        edge=('HipFat.outputY','|Group|FitSkeleton|Root|Hip.fatFrontAbs')
        self.assertTrue(_missing_fit_fat_connection(host,edge,'|Group|FitSkeleton'))
        commands.connectionInfo.return_value='UserDriver.output'
        self.assertFalse(_missing_fit_fat_connection(host,edge,'|Group|FitSkeleton'))
        commands.connectionInfo.return_value=''
        self.assertFalse(_missing_fit_fat_connection(host,
            ('HipFat.outputX','|Group|FitSkeleton|Root|Hip.fatFrontAbs'),'|Group|FitSkeleton'))

    def test_role_alias_maps_reparented_controller_edges(self):
        commands=Mock()
        commands.nodeType.return_value='transform'
        host=SimpleNamespace(_cmds=commands)
        edges=(('|old|control.message','AdvPy_CharacterRegistry.members[1]'),)
        with patch('adv_py.adapters.maya_character_ownership.connections',return_value=edges):
            nodes,links=_graph(host,('|old|control','AdvPy_CharacterRegistry'),
                roles={'|old|control':'|new|control'},normalize_registry=True)
        self.assertEqual(nodes['|new|control'],'|old|control')
        self.assertEqual(links,(('|new|control.message','AdvPy_CharacterRegistry.members[*]'),))
