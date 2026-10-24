"""Detached NonSym end-joint decisions survive a staged namespace build."""
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS

from adv_py.core.fit_hierarchy import FitHierarchyNode,FitHierarchySnapshot
from adv_py.core.source_fit_terminal import SourceFitTerminalState,source_fit_terminal_state
from adv_py.core.fit_settings import FitSkeletonValidationError


def hierarchy(container='|Group|FitSkeleton',namespace=''):
    root=container+'|'+namespace+'Root'
    tip=root+'|'+namespace+'Tip_NonSymmetry'
    return FitHierarchySnapshot(container,(
        FitHierarchyNode(root,namespace+'Root',container,(0.,0.,0.),(0.,0.,0.)),
        FitHierarchyNode(tip,namespace+'Tip_NonSymmetry',root,(0.,2.,0.),(0.,2.,0.))))


class SourceFitTerminalTests(unittest.TestCase):
    def test_state_rebases_container_and_namespace_without_inventing_a_child(self):
        original=hierarchy()
        saved=source_fit_terminal_state(original,(original.joints[-1].path,))
        stage=hierarchy('|stage:FitSkeleton','stage:')
        self.assertEqual(saved.resolve(stage),(stage.joints[-1].path,))
        self.assertEqual(saved.resolve(hierarchy('|stage:Group|stage:FitSkeleton','stage:')),
                         ('|stage:Group|stage:FitSkeleton|stage:Root|stage:Tip_NonSymmetry',))
        self.assertEqual(len(stage.joints),2)

    def test_source_or_replacement_with_different_fit_identity_is_rejected(self):
        original=hierarchy()
        with self.assertRaises(FitSkeletonValidationError):
            source_fit_terminal_state(original,('|Other|Tip_NonSymmetry',))
        saved=source_fit_terminal_state(original,(original.joints[-1].path,))
        changed=replace(original,joints=original.joints[:1])
        with self.assertRaises(FitSkeletonValidationError):saved.resolve(changed)

    def test_staged_reader_uses_snapshot_instead_of_global_legacy_container(self):
        from adv_py.adapters.maya_source_fit_terminal import capture_non_terminal_fits
        stage=hierarchy('|stage:FitSkeleton','stage:')
        class Commands:
            def objExists(self,*args):raise AssertionError('cross-character scene lookup')
        host=NS(_cmds=Commands(),_source_fit_terminal_state=SourceFitTerminalState((('Root','Tip_NonSymmetry'),)))
        self.assertEqual(capture_non_terminal_fits(host,stage),(stage.joints[-1].path,))

    def test_staged_snapshot_is_checked_against_imported_fit_before_installation(self):
        from adv_py.adapters.maya_source_fit_terminal import install_staged_state
        stage=hierarchy('|stage:FitSkeleton','stage:')
        host=NS(_require_transaction=lambda:None,capture_fit_hierarchy=lambda _:stage)
        saved=SourceFitTerminalState((('Root','Tip_NonSymmetry'),))
        install_staged_state(host,saved)
        self.assertEqual(host._source_fit_terminal_state,saved)
        with self.assertRaises(FitSkeletonValidationError):
            install_staged_state(host,SourceFitTerminalState((('Root','Missing'),)))
        self.assertEqual(host._source_fit_terminal_state,saved)

    def test_closed_relative_identity_rejects_scene_addresses_and_duplicates(self):
        for raw in ((('Root','bad.name'),),(('Root','ns:Tip'),),(('Root',),('Root',))):
            with self.assertRaises(FitSkeletonValidationError):SourceFitTerminalState(raw)

    def test_detached_child_enables_fk_for_both_body_sides_without_fake_children(self):
        from adv_py.core.body_generic_fk import plan_body_generic_fk
        from adv_py.core.body_skeleton import BodyJointSpec,BodyJointState,BodySkeletonSnapshot
        from adv_py.core.fit_metadata import FitJointMetadata
        from adv_py.core.fit_symmetry import FitBuildSide
        source='|FitSkeleton|Root|Tip'
        specs=[];states=[]
        for side in (FitBuildSide.RIGHT,FitBuildSide.LEFT):
            name='Tip_'+side.value;path='|Body|'+name
            specs.append(BodyJointSpec(source,path,name,'|Body',side,(0.,2.,0.),None))
            states.append(BodyJointState(path,name,'|Body',side,(0.,2.,0.),None,(0.,0.,0.),(0.,0.,0.)))
        body=BodySkeletonSnapshot('|Body',tuple(states),fit_height=10.)
        args=(body,tuple(specs),(FitJointMetadata(source),),())
        flags=dict(sub_controllers=False,extra_controllers=False)
        self.assertEqual(plan_body_generic_fk(*args,**flags).controls,())
        actual=plan_body_generic_fk(*args,**flags,non_terminal_sources=frozenset((source,)))
        self.assertEqual({control.driven_joint for control in actual.controls},{state.path for state in states})
        self.assertTrue(all(control.aim_path is None for control in actual.controls))


if __name__=='__main__':unittest.main()
