"""Native persistent endpoint parent and distance-order branch checks."""
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS

from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.fit_hierarchy import FitHierarchyNode, FitHierarchySnapshot
from adv_py.core.source_spline_alignment import (
    SourceSplineAlignmentFrame, plan_source_spline_alignment_frames,
    encode_source_spline_alignment, decode_source_spline_alignment,
)
from adv_py.core.source_spline_animation import source_spline_nearest_deform
from adv_py.core.source_spline_rebuild import retain_source_spline_layout


def fixture(side='M',has_end_child=False):
    names=('Root','Spine','Chest')+ (('Head',) if has_end_child else ())
    fit_paths=[]; body_paths=[]; controls=[]; instances=[]; drivers=[]
    for name in names:
        fit_paths.append((fit_paths[-1] if fit_paths else '|FitSkeleton')+'|'+name)
        body_paths.append((body_paths[-1] if body_paths else '|Group|DeformationSystem')+'|'+name+'_'+side)
        path='|Group|MotionSystem|FK'+name+'_'+side
        driver='|Group|Spline|Driver'+name+'_'+side
        controls.append(NS(driven_joint=driver,control_path=path,control_name='FK'+name+'_'+side,
            source_override_path=path+'|FKX'+name+'_'+side,sub_control_path=None))
        drivers.append(NS(path=driver,source_joint=body_paths[-1]))
        instances.append(NS(source_joint=fit_paths[-1],output_name=name+'_'+side))
    hierarchy=FitHierarchySnapshot('|FitSkeleton',tuple(FitHierarchyNode(path,names[index],
        fit_paths[index-1] if index else '|FitSkeleton',(0.,1.,0.),(0.,float(index),0.))
        for index,path in enumerate(fit_paths)))
    plan=BodySplinePlan('|Group|Spline',tuple(drivers[:3]),tuple(body_paths[:3]),
        tuple(control.control_path for control in controls[:3]),controls[0].control_path,'|ChestSpace',
        ('|IK0','|IK1'),((0.,0.,0.),(0.,2.,0.)),(),(1.,1.),
        source_curve_points=((0.,0.,0.),)*3,source_alignment_frames=True)
    return plan,NS(controls=tuple(controls)),hierarchy,tuple(instances)


class SourceSplineAlignmentTests(unittest.TestCase):
    def test_terminal_endpoint_attaches_to_fit_parent_fkx(self):
        plan,fk,hierarchy,instances=fixture()
        frames=plan_source_spline_alignment_frames(plan,fk,(plan,),hierarchy,instances)
        self.assertEqual(frames[0].parent,fk.controls[0].source_override_path)
        self.assertEqual(frames[1].parent,fk.controls[1].source_override_path)
        self.assertEqual(frames[1].target,frames[1].parent+'|AlignIKToChest_M')

    def test_endpoint_with_child_uses_its_own_fkx(self):
        plan,fk,hierarchy,instances=fixture(has_end_child=True)
        frames=plan_source_spline_alignment_frames(plan,fk,(plan,),hierarchy,instances)
        self.assertEqual(frames[1].parent,fk.controls[2].source_override_path)

    def test_detached_nonsym_previous_parent_keeps_own_endpoint_fkx(self):
        from adv_py.core.source_fit_identity import source_fit_is_end_joint
        plan,fk,hierarchy,instances=fixture()
        end=hierarchy.joints[-1].path
        self.assertTrue(source_fit_is_end_joint(hierarchy,end))
        self.assertFalse(source_fit_is_end_joint(hierarchy,end,(end,)))
        frames=plan_source_spline_alignment_frames(plan,fk,(plan,),hierarchy,instances,non_terminal_fit=(end,))
        self.assertEqual(frames[1].parent,fk.controls[2].source_override_path)

    def test_native_nonsym_container_reads_only_direct_joint_previous_parent(self):
        from adv_py.adapters.maya_source_spline_alignment import capture_non_terminal_fits
        _,_,hierarchy,_=fixture()
        end=hierarchy.joints[-1].path
        class Commands:
            def objExists(self,node):return node in ('NonSymmetryFitJoints','|NonSym|Added.previousParent')
            def listRelatives(self,node,**flags):
                self.flags=flags;return ['|NonSym|Added','|NonSym|Unrelated']
            def getAttr(self,plug):return 'Chest'
            def ls(self,node,**flags):return [end,'|Other|Chest']
        commands=Commands()
        self.assertEqual(capture_non_terminal_fits(NS(_cmds=commands),hierarchy),(end,))
        self.assertEqual(commands.flags,dict(children=True,type='joint',fullPath=True))

    def test_left_terminal_retains_same_side_parent(self):
        plan,fk,hierarchy,instances=fixture(side='L')
        frames=plan_source_spline_alignment_frames(plan,fk,(plan,),hierarchy,instances)
        self.assertTrue(frames[-1].parent.endswith('FKXSpine_L'))
        self.assertTrue(frames[-1].target.endswith('AlignIKToChest_L'))

    def test_base_fk_receiver_does_not_steal_parent_identity(self):
        plan,fk,hierarchy,instances=fixture()
        helper=NS(**{**vars(fk.controls[1]),'control_name':'AdvPy_SplineBaseFK',
            'control_path':'|Helper','source_override_path':'|Helper|HelperX'})
        fk=NS(controls=(*fk.controls,helper))
        frames=plan_source_spline_alignment_frames(plan,fk,(plan,),hierarchy,instances)
        self.assertEqual(frames[1].parent,fk.controls[1].source_override_path)

    def test_same_layout_rebuild_preserves_legacy_flag(self):
        plan,_,_,_=fixture()
        old=replace(plan,source_alignment_frames=False)
        self.assertFalse(retain_source_spline_layout(plan,old).source_alignment_frames)
        self.assertTrue(retain_source_spline_layout(plan,old,change_count=True).source_alignment_frames)

    def test_missing_fit_identity_is_rejected(self):
        plan,fk,hierarchy,_=fixture()
        with self.assertRaises(CharacterRegistryError):
            plan_source_spline_alignment_frames(plan,fk,(plan,),hierarchy,())

    def test_closed_record_roundtrip_and_body_converter_rename(self):
        frames=(SourceSplineAlignmentFrame('|Body|Root_M','|RootX','|RootX|AlignIKToRoot_M'),
                SourceSplineAlignmentFrame('|Body|Chest_M','|ChestX','|ChestX|AlignIKToChest_M'))
        encoded=encode_source_spline_alignment(frames)
        self.assertEqual(decode_source_spline_alignment(encoded),frames)
        raw=json.loads(encoded);raw['frames'][1]['body']='|Body|spine_03'
        self.assertEqual(decode_source_spline_alignment(json.dumps(raw))[1].target,frames[1].target)
        raw['frames'][1]['target']='|Other|AlignIKToChest_M'
        with self.assertRaises(CharacterRegistryError):
            decode_source_spline_alignment(json.dumps(raw))

    def test_native_distance_uses_namespace_to_break_ties(self):
        result=source_spline_nearest_deform((0.,0.,0.),(
            ('|D|z:A_M',(1.,0.,0.)),('|D|a:Z_M',(1.0001,0.,0.))))
        self.assertEqual(result,'|D|a:Z_M')

    def test_native_five_digit_text_width_is_not_numeric_sort(self):
        result=source_spline_nearest_deform((0.,0.,0.),(
            ('|D|A_M',(99999.,0.,0.)),('|D|B_M',(100000.,0.,0.))))
        self.assertEqual(result,'|D|B_M')

    def test_native_deform_exclusions(self):
        result=source_spline_nearest_deform((0.,0.,0.),(
            ('|D|Arm_L',(0.,0.,0.)),('|D|Partial_Arm_R',(0.,0.,0.)),
            ('|D|ArmFix_R',(0.,0.,0.)),('|D|Arm_R',(2.,0.,0.))))
        self.assertEqual(result,'|D|Arm_R')


class SceneCommands:
    def __init__(self):
        self.nodes={};self.attrs={};self.locks={};self.calls=[]
    def objExists(self,value):return value in self.attrs or bool(self.ls(value))
    def ls(self,value,**flags):
        found=[node for node in self.nodes if node==value or node.rsplit('|',1)[-1]==value]
        return [self.nodes[node] for node in found] if flags.get('uuid') else found
    def createNode(self,kind,**flags):
        name='|'+flags['name'];self.nodes[name]='uuid:'+name;self.calls.append(('create',name));return name
    def getAttr(self,plug,**flags):
        if flags.get('lock'):return self.locks.get(plug,False)
        if flags.get('type'):return 'string'
        return self.attrs.get(plug,0)
    def setAttr(self,plug,*values,**flags):
        if values:self.attrs[plug]=values[0]
        if 'lock' in flags:self.locks[plug]=flags['lock']
        self.calls.append(('set',plug,values,flags))
    def xform(self,node,**flags):
        self.calls.append(('xform',node,flags))
        if flags.get('query'):
            if flags.get('rotateOrder'):return 'zyx'
            return (1.,2.,3.) if flags.get('translation') else (4.,5.,6.)
    def parent(self,node,parent,**flags):
        target=parent+'|'+node.rsplit('|',1)[-1]
        self.nodes[target]=self.nodes.pop(node);return [target]
    def addAttr(self,node,**flags):self.attrs[node+'.'+flags['longName']]=''
    def listRelatives(self,node,**flags):return [node.rsplit('|',1)[0]]


class SourceSplineAlignmentSceneTests(unittest.TestCase):
    def setup_scene(self):
        plan,fk,hierarchy,instances=fixture()
        plan=replace(plan,source_mode=NS(control='|Mode'))
        commands=SceneCommands()
        for body in plan.body_joints:commands.nodes[body]='uuid:'+body
        host=NS(_cmds=commands,_transaction_changed=False,_require_transaction=lambda:None)
        return host,plan,fk,hierarchy,instances

    def test_create_and_shared_endpoint_reuse_do_not_overwrite_rest_frame(self):
        from adv_py.adapters.maya_source_spline_alignment import create,read
        host,plan,fk,hierarchy,instances=self.setup_scene()
        frames=create(host,plan,fk,(plan,),hierarchy,instances)
        self.assertEqual(read(host,plan),frames)
        count=len([row for row in host._cmds.calls if row[0]=='create'])
        second=replace(plan,source_mode=NS(control='|OtherMode'))
        self.assertEqual(create(host,second,fk,(plan,),hierarchy,instances),frames)
        self.assertEqual(len([row for row in host._cmds.calls if row[0]=='create']),count)
        self.assertFalse(any(row[0]=='xform' and 'rotation' in row[2] for row in host._cmds.calls))

    def test_existing_unowned_transform_is_not_adopted(self):
        from adv_py.adapters.maya_source_spline_alignment import create
        host,plan,fk,hierarchy,instances=self.setup_scene()
        frame=plan_source_spline_alignment_frames(plan,fk,(plan,),hierarchy,instances)[0]
        host._cmds.nodes[frame.target]='foreignUUID'
        with self.assertRaises(CharacterRegistryError):create(host,plan,fk,(plan,),hierarchy,instances)

    def test_replaced_body_identity_is_detected(self):
        from adv_py.adapters.maya_source_spline_alignment import create,read
        host,plan,fk,hierarchy,instances=self.setup_scene()
        create(host,plan,fk,(plan,),hierarchy,instances)
        host._cmds.nodes[plan.body_joints[-1]]='replacementUUID'
        with self.assertRaises(CharacterRegistryError):read(host,plan)

    def test_native_endpoint_query_does_not_import_maya_api(self):
        from adv_py.adapters.maya_source_spline_alignment import create
        from adv_py.adapters.maya_source_spline_matching import _endpoint_rotation
        host,plan,fk,hierarchy,instances=self.setup_scene()
        create(host,plan,fk,(plan,),hierarchy,instances)
        self.assertEqual(_endpoint_rotation(host,None,NS(plan=plan),1),(4.,5.,6.))
        self.assertTrue(any(row[0]=='xform' and row[2].get('preserve')
                            and row[2].get('rotateOrder')=='zyx' for row in host._cmds.calls))


if __name__=='__main__':
    unittest.main()
