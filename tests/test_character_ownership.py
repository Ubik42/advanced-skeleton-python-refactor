import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from adv_py.adapters.maya_character_ownership import _graph,_missing_fit_fat_connection,_source_fit_driving_edges,_source_rp_reverse_ownership_edges


class CharacterOwnershipTests(unittest.TestCase):
    def test_old_fk_follower_adds_only_registered_body_message_role(self):
        from adv_py.adapters.maya_character_ownership import _source_fk_follower_ownership_edges
        from adv_py.core.character_registry import CharacterRegistryError
        body='|Body|Root_M'
        follower='|Motion|AdvPy_GenericFKFollow_Hip_L'
        row=SimpleNamespace(path=follower,node_type='transform')
        registration=SimpleNamespace(body=(SimpleNamespace(path=body),),retired_body=(),nodes=(row,))
        host=SimpleNamespace(_cmds=SimpleNamespace(objExists=lambda plug:False))
        target=SimpleNamespace(_cmds=SimpleNamespace(objExists=lambda plug:True,
            listConnections=lambda *args,**flags:[body],ls=lambda *args,**flags:[body],
            getAttr=lambda plug,**flags:'message' if flags.get('type') else True,
            isConnected=lambda *args:True))
        plug=follower+'.advPySourceFkFollowerScaleBody'
        self.assertEqual(_source_fk_follower_ownership_edges(host,target,registration,registration),
                         frozenset(((body+'.message',plug),)))
        target._cmds.ls=lambda *args,**flags:['|Foreign|Joint']
        with self.assertRaises(CharacterRegistryError):
            _source_fk_follower_ownership_edges(host,target,registration,registration)

    def test_alignment_migration_owns_only_selected_new_reference_frames(self):
        from adv_py.adapters.maya_character_ownership import _source_spline_alignment_additions
        from adv_py.core.character_registry import CharacterRegistryError
        old=SimpleNamespace()
        spine=SimpleNamespace(system_name='Spine_M')
        tail=SimpleNamespace(system_name='Tail_L')
        new=SimpleNamespace(spine=spine,additional_spines=(tail,))
        host=SimpleNamespace(_cmds=SimpleNamespace(objExists=lambda node: node.endswith('Existing')))
        target=SimpleNamespace(_cmds=SimpleNamespace(nodeType=lambda node:'transform'))
        with patch('adv_py.core.source_spline_alignment_upgrade.audit_source_spline_alignment_upgrade') as gate, \
             patch('adv_py.adapters.maya_source_spline_alignment.read',return_value=(
                 SimpleNamespace(target='|FK|AlignIKToNew'),SimpleNamespace(target='|FK|AlignIKToExisting'))) as read:
            self.assertEqual(_source_spline_alignment_additions(host,target,old,new,('Spine_M',)),
                             frozenset(('|FK|AlignIKToNew',)))
            gate.assert_called_once_with(old,new,('Spine_M',))
            read.assert_called_once_with(target,spine)
            target._cmds.nodeType=lambda node:'joint'
            with self.assertRaises(CharacterRegistryError):
                _source_spline_alignment_additions(host,target,old,new,('Spine_M',))
        self.assertEqual(_source_spline_alignment_additions(host,target,old,new,()),frozenset())

    def test_legacy_rp_upgrade_is_only_the_saved_native_reverse_message(self):
        from test_source_limb_mode import SourceLimbModeTests
        from dataclasses import asdict
        from adv_py.core.character_registry import canonical, CharacterRegistryError
        plan = SourceLimbModeTests().plan()
        registration = SimpleNamespace(
            channels=(SimpleNamespace(key='arm', node=plan.source_mode.control,
                                      attribute='FKIKBlend'),),
            source_limbs=(SimpleNamespace(blend_key='arm'),))
        host = SimpleNamespace(_cmds=SimpleNamespace(
            getAttr=lambda plug: canonical(asdict(plan)), nodeType=lambda node: 'reverse'))
        self.assertEqual(_source_rp_reverse_ownership_edges(host, registration), frozenset((
            ('FKIKBlendArm_RReverse.message',
             plan.source_mode.control + '.advPySourceRpModeReverse'),)))
        host._cmds.nodeType = lambda node: 'multiplyDivide'
        with self.assertRaises(CharacterRegistryError):
            _source_rp_reverse_ownership_edges(host, registration)
        registration.channels[0].attribute = 'armIkFk_R'
        self.assertEqual(_source_rp_reverse_ownership_edges(host, registration), frozenset())

    def test_native_fit_catalogue_allows_only_declared_live_curve_links(self):
        from adv_py.adapters.maya_body_driving_fit import (
            DrivingFitPlan, DrivingFitControl, DrivingFitAttribute)
        control = DrivingFitControl('hero:Fingers_L', 'drivingSystem_Fingers_L', (
            DrivingFitAttribute('spread', ('hero:SDKFKIndexFinger1_L_rotateZ1',)),
            DrivingFitAttribute('cup', ('hero:SDKFKCup_L_rotateX1',))))
        from adv_py.core.character_identity import CharacterIdentity
        host = SimpleNamespace(
            plan_body_driving_fit_sync=lambda fit: DrivingFitPlan(fit, (control,)),
            _cmds=SimpleNamespace(nodeType=lambda curve: 'animCurveUA',
                                 identity=CharacterIdentity('hero')))
        registration = SimpleNamespace(container='|Group|FitSkeleton')
        self.assertEqual(_source_fit_driving_edges(host, registration), frozenset((
            ('|Group|FitSkeleton.drivingSystem_Fingers_L[0]', 'SDKFKIndexFinger1_L_rotateZ1.spread'),
            ('|Group|FitSkeleton.drivingSystem_Fingers_L[1]', 'SDKFKCup_L_rotateX1.cup'))))
        host._cmds.nodeType = lambda curve: 'multiplyDivide'
        from adv_py.core.character_registry import CharacterRegistryError
        with self.assertRaises(CharacterRegistryError):
            _source_fit_driving_edges(host, registration)

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
