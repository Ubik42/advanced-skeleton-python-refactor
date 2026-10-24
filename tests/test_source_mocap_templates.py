"""Bundled custom zero-out values and separate native motion templates."""
from types import SimpleNamespace
import unittest

from adv_py.adapters.maya_source_name_matcher import source_name_matcher_catalog,source_name_matcher_template_path
from adv_py.adapters.maya_source_mocap_templates import apply_zero_out_hook
from adv_py.core.source_name_matcher import read_source_name_matcher_template
from adv_py.adapters.maya_source_name_matcher_controls import MayaSourceNameMatcherControlsMixin
from adv_py.core.name_matcher_fit import NameMatcherRow,NameMatcherRules


class SourceMocapTemplateTests(unittest.TestCase):
    def host(self,existing):
        calls=[]
        commands=SimpleNamespace(objExists=lambda name:name in existing,
            setAttr=lambda plug,*values,**flags:calls.append((plug,values,flags)))
        return SimpleNamespace(_cmds=commands),calls

    def test_mocap_catalog_is_the_native_directory_and_every_template_parses(self):
        catalog=source_name_matcher_catalog(mocap=True)
        self.assertTrue(catalog)
        self.assertTrue(all(path.parent.name=='moCapMatchers' for path in catalog))
        templates={path.stem:read_source_name_matcher_template(path.read_text(encoding='utf-8-sig'))
                   for path in catalog}
        self.assertIn('MotionBuilder',templates);self.assertIn('Plask',templates)
        self.assertNotIn('Unreal5',templates)
        self.assertNotEqual(source_name_matcher_template_path('Mixamo',mocap=True),
                            source_name_matcher_template_path('Mixamo'))

    def test_mixamo_zeros_the_unmapped_spine_without_changing_its_parent(self):
        host,calls=self.host({'take:Spine'})
        self.assertEqual(apply_zero_out_hook(host,'Mixamo','take'),('take:Spine.rotate',))
        self.assertEqual(calls,[('take:Spine.rotate',(0.,0.,0.),{'type':'float3'})])
        self.assertTrue(host._transaction_changed)

    def test_plask_preserves_literal_namespace_concatenation_and_source_values(self):
        names={'hips','rightUpLeg','leftUpLeg','rightFoot','leftFoot','rightShoulder','leftShoulder'}
        host,calls=self.host(names)
        self.assertEqual(len(apply_zero_out_hook(host,'Plask','')),7)
        self.assertEqual(calls[0],('hips.rotate',(-90.,0.,90.),{'type':'float3'}))
        self.assertEqual(calls[1],('rightUpLeg.rotateZ',(180.,),{}))
        self.assertEqual(calls[-1],('leftShoulder.rotate',(-90.,-90.,0.),{'type':'float3'}))
        # The bundled custom MEL does not insert ':' for Plask. Keep that
        # behavior even though a different naming convention may be desired.
        host,calls=self.host({'take:hips'})
        self.assertEqual(apply_zero_out_hook(host,'Plask','take'),())
        self.assertFalse(calls)

    def test_native_custom_procedure_does_not_swallow_locked_attr_failure(self):
        host,_=self.host({'take:Spine'})
        def locked(*args,**flags):raise RuntimeError('locked')
        host._cmds.setAttr=locked
        with self.assertRaisesRegex(RuntimeError,'locked'):apply_zero_out_hook(host,'Mixamo','take')

    def test_mocap_collision_uses_last_full_path_outside_group_and_keeps_order(self):
        body=('|Group|DeformationSystem|Root_M|Wrist_R','|Group|DeformationSystem|Root_M')
        commands=SimpleNamespace(listRelatives=lambda *args,**flags:body,
            ls=lambda target,**flags: (['|Group|hand','|takeA|hand','|takeB|hand']
                                      if target=='hand' else ['|takeB|hips']))
        host=SimpleNamespace(_cmds=commands)
        result=MayaSourceNameMatcherControlsMixin.plan_source_name_matcher_mocap_mapping(host,'|takeB|hips',
            (NameMatcherRow('Root','hips'),NameMatcherRow('Wrist','hand')),NameMatcherRules('','',''))
        self.assertEqual(tuple((pair.advanced_joint,pair.external_joint) for pair in result.pairs),
            ((body[0],'|takeB|hand'),(body[1],'|takeB|hips')))


if __name__=='__main__':unittest.main()
