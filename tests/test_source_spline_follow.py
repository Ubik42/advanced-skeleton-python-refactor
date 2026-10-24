"""Native Spline uses physical Body parenting and separate Fit levels."""
from dataclasses import dataclass
from types import SimpleNamespace as Row
import unittest
from adv_py.core.source_spline_follow import configure_source_spline_follow

@dataclass(frozen=True)
class Plan:
    body_joints: tuple
    system_name: str = ''
    targets: tuple = ('|Controls|A', '|Controls|B')
    sub_targets: tuple = ()
    source_follow_parent: str | None = None
    source_follow_targets: tuple = ()
    source_native_follow: bool = False
    def target_parent(self, index): return '|Controls'

class SourceSplineFollowTests(unittest.TestCase):
    def fixture(self, *, physical_part=True, non_symmetry=False):
        root='|Body|Root_M'; chest=root+'|Chest_M'; head=chest+'|Head_M'
        parent=head+'|HeadPart1_L' if physical_part else head
        start=parent+'|Tail_L'
        joints=tuple(Row(name=name,path=path,parent_path=up) for name,path,up in
            (('Root_M',root,'|Body'),('Chest_M',chest,root),('Head_M',head,chest),('Tail_L',start,head)))
        fit_head='|Fit|Root|Chest|Head'
        fit_start=fit_head+'|Tail'
        nodes=[Row(path=fit_head,short_name='Head',dag_parent='|Fit|Root|Chest'),
               Row(path=fit_start,short_name='Tail',dag_parent=fit_head)]
        actual='|Fit|Head_NonSymmetry|Tail_NonSymmetry' if non_symmetry else fit_start
        if non_symmetry:
            nodes.append(Row(path=actual,short_name='Tail_NonSymmetry',dag_parent='|Fit|Head_NonSymmetry'))
        body=Row(root=root,joints=joints)
        fk=Row(controls=(Row(driven_joint=root,control_path='|RootFK',source_override_path=None),))
        main=Row(control_path='|Main',extra_control_paths=('|MainExtra1','|MainExtra2'))
        hierarchy=Row(joints=tuple(nodes))
        instances=(Row(output_name='Tail_L',source_joint=actual),)
        return Plan((start,)),body,fk,main,hierarchy,instances

    def test_part_parent_drives_offset_but_fit_parent_drives_follow_level(self):
        plan,body,fk,main,hierarchy,instances=self.fixture()
        result=configure_source_spline_follow(plan,body,fk,main,hierarchy=hierarchy,instances=instances)
        self.assertEqual(result.source_follow_parent,plan.body_joints[0].rsplit('|',1)[0])
        self.assertEqual([x[0] for x in result.source_follow_targets],
                         ['MainExtra2','MainExtra1','Main','Root','Chest','Head'])
        self.assertEqual([x[2] for x in result.source_follow_targets],[0.,0.,10.,10.,0.,10.])
        self.assertEqual(result.source_follow_targets[-1][1],body.joints[2].path)

    def test_non_symmetry_uses_authored_ancestry_and_unsuffixed_parent_query(self):
        plan,body,fk,main,hierarchy,instances=self.fixture(non_symmetry=True)
        result=configure_source_spline_follow(plan,body,fk,main,hierarchy=hierarchy,instances=instances)
        self.assertNotIn('Chest',[x[0] for x in result.source_follow_targets])
        self.assertEqual(result.source_follow_targets[-1],('Head',body.joints[2].path,10.))

    def test_direct_root_child_and_root_start_keep_native_sources(self):
        for root_start in (False,True):
            plan,body,fk,main,_,_=self.fixture()
            start=body.root if root_start else body.root+'|Tail_L'
            body.joints=body.joints[:1]+(Row(name='Tail_L',path=start,parent_path=body.root),)
            from dataclasses import replace
            result=configure_source_spline_follow(replace(plan,body_joints=(start,)),body,fk,main,
                root_control_path='|RootX',root_follow_path='|LegLock')
            self.assertEqual(result.source_follow_parent,'|RootX' if root_start else '|LegLock')

    def test_part_legacy_input_bypasses_exact_part_token_only(self):
        plan,body,fk,main,_,_=self.fixture()
        body.joints[-1].parent_path=plan.body_joints[0].rsplit('|',1)[0]
        result=configure_source_spline_follow(plan,body,fk,main)
        self.assertEqual(result.source_follow_targets[-1][0],'Head')

if __name__=='__main__': unittest.main()
