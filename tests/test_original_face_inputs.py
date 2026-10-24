"""Source input selection, Skin confirmation and per-eye lattice behavior."""
import unittest
from contextlib import nullcontext

from adv_py.adapters.maya_original_face_inputs import MayaOriginalFaceInputsMixin
from adv_py.core.fit_settings import FitSkeletonValidationError


class Commands:
    def __init__(self):
        self.selection=[];self.history={};self.types={};self.calls=[]
        self.existing={'FaceFitSkeleton','FaceFitSkeletonShape','FaceFitSkeletonHeightShape'}
        self.answers=['Create New SkinCluster'];self.attrs={}
        self.descendants={};self.shapes={};self.aliases={}
    def ls(self,nodes=None,**flags):
        if flags.get('selection'):return self.selection
        if isinstance(nodes,str):return self.aliases.get(nodes,[nodes])
        return list(nodes or [])
    def objExists(self,node):return node in self.existing or node in self.attrs
    def select(self,*args,**flags):self.calls.append(('select',args,flags))
    def listRelatives(self,node,**flags):
        return self.descendants.get(node,[]) if flags.get('allDescendents') else self.shapes.get(node,[])
    def nodeType(self,node):return self.types[node]
    objectType=nodeType
    def listHistory(self,node,**flags):return self.history.get(node,[])
    def confirmDialog(self,**flags):
        self.calls.append(('dialog',flags));return self.answers.pop(0)
    def joint(self,**flags):
        self.existing.add(flags['name']);self.calls.append(('joint',flags));return flags['name']
    def xform(self,node,**flags):
        self.calls.append(('xform',node,flags))
        if flags.get('query'):
            return (0.,3.,0.) if node=='FaceFitSkeletonShape.cv[0]' else (0.,15.,0.)
    def skinCluster(self,*args,**flags):
        self.calls.append(('skin',args,flags));return ['newSkin']
    def listAttr(self,node,**flags):return ['asNonSphereLattice_L','userAttribute']
    def deleteAttr(self,plug):self.calls.append(('deleteAttr',plug))
    def addAttr(self,node,**flags):
        self.attrs[node+'.'+flags['longName']]='';self.calls.append(('addAttr',node,flags))
    def reorderDeformers(self,*args):self.calls.append(('reorder',args))
    def getAttr(self,plug,**flags):return self.attrs.get(plug,0)
    def setAttr(self,plug,*args,**flags):
        if args:self.attrs[plug]=args[0]
        self.calls.append(('setAttr',plug,args,flags))
    def referenceQuery(self,node,**flags):return False


class Host(MayaOriginalFaceInputsMixin):
    def __init__(self):self._cmds=Commands();self._transaction_changed=False
    def _require_transaction(self):pass
    def scene_address(self,node):return node
    def _fit(self,**flags):return 'FaceFitSkeleton'


class OriginalFaceInputTests(unittest.TestCase):
    def test_group_selection_uses_transform_descendants_and_first_shape(self):
        host=Host();c=host._cmds;c.selection=['|Group'];c.aliases={'Group':['|Group']}
        c.descendants={'|Group':['|Group|Face','|Group|Curve']}
        c.shapes={'|Group|Face':['faceShape'],'|Group|Curve':['curveShape']}
        c.types={'faceShape':'mesh','curveShape':'nurbsCurve'}
        self.assertEqual(host.selected_original_face_geometry(),('|Group|Face',))
        self.assertEqual(host.original_face_geometry(('|Group',),allow_components=True),('|Group|Face',))

    def test_reserved_and_ambiguous_names_are_rejected(self):
        for selected,aliases in (('|Group|Eye_R',{}),('|A|Face',{'Face':['|A|Face','|B|Face']})):
            host=Host();host._cmds.selection=[selected];host._cmds.aliases=aliases
            with self.assertRaises(FitSkeletonValidationError):host.selected_original_face_geometry()

    def test_object_input_rejects_components_but_parts_keep_selection(self):
        host=Host();c=host._cmds;c.selection=['|Face.vtx[2]'];c.aliases={'Face':['|Face']}
        with self.assertRaises(FitSkeletonValidationError):host.selected_original_face_geometry()
        self.assertEqual(host.selected_original_face_geometry(allow_components=True),('|Face.vtx[2]',))

    def test_native_last_history_skin_wins_without_head_influence_filter(self):
        host=Host();c=host._cmds;c.history={'mesh':['skin1','ffd','skin2']}
        c.types={'skin1':'skinCluster','ffd':'ffd','skin2':'skinCluster'}
        self.assertEqual(host.ensure_original_face_input_skins(('mesh',)),('skin2',))
        self.assertFalse(host._transaction_changed)
        self.assertEqual(c.calls,[])

    def test_cancel_does_not_create_head_or_skin(self):
        host=Host();c=host._cmds;c.answers=['Cancel']
        self.assertIsNone(host.ensure_original_face_input_skins(('mesh',)))
        self.assertFalse(host._transaction_changed)
        self.assertFalse(any(row[0] in ('joint','skin') for row in c.calls))

    def test_native_head_height_and_skin_flags_and_one_skin_confirmation(self):
        host=Host();c=host._cmds
        self.assertEqual(host.ensure_original_face_input_skins(('mesh1','mesh2')),('newSkin','newSkin'))
        self.assertEqual(len([row for row in c.calls if row[0]=='dialog']),1)
        self.assertEqual(len([row for row in c.calls if row[0]=='joint']),1)
        head_moves=[row for row in c.calls if row[0]=='xform' and row[1]=='Head_M']
        self.assertEqual(head_moves[0][2]['translation'],(0,7.,0))
        skins=[row for row in c.calls if row[0]=='skin']
        self.assertEqual(skins[0][2],dict(toSelectedBones=True,maximumInfluences=1,
                                        dropoffRate=4,removeUnusedInfluence=False))
        self.assertIn(('setAttr','FaceFitSkeleton.HeadJoint',('Head_M',),{'type':'string'}),c.calls)

    def test_choose_head_records_first_joint_and_does_not_require_mask_shape(self):
        host=Host();c=host._cmds;c.selection=['|Bones|Head','|Bones|Other']
        c.aliases={'Head':['|Bones|Head'],'Other':['|Bones|Other']}
        c.types={'|Bones|Head':'joint','|Bones|Other':'joint'}
        c.existing.remove('FaceFitSkeletonShape')
        self.assertEqual(host.record_original_face_head_joint(),'|Bones|Head')
        self.assertIn(('setAttr','FaceFitSkeleton.HeadJoint',('Head',),{'type':'string'}),c.calls)
        self.assertFalse(any(row[0]=='skin' for row in c.calls))

    def test_choose_head_rejects_a_transform_before_attribute_write(self):
        host=Host();c=host._cmds;c.selection=['|Object'];c.aliases={'Object':['|Object']}
        c.types={'|Object':'transform'}
        with self.assertRaises(FitSkeletonValidationError):host.record_original_face_head_joint()
        self.assertFalse(host._transaction_changed)

    def eye_scene(self):
        host=Host();c=host._cmds;c.selection=['|EyeMesh'];c.aliases={'EyeMesh':['|EyeMesh']}
        c.shapes={'|EyeMesh':['eyeShape']};c.types={'eyeShape':'mesh','skin':'skinCluster'}
        c.history={'|EyeMesh':['skin']}
        return host

    def test_pre_eye_records_skin_input_without_building_fit(self):
        host=self.eye_scene();c=host._cmds
        self.assertEqual(host.record_original_face_eye_input('Left'),('|EyeMesh',))
        self.assertEqual(c.attrs['FaceFitSkeleton.LeftEye'],'|EyeMesh')
        self.assertNotIn('FaceFitSkeleton.RightEye',c.attrs)
        self.assertFalse(any(row[0] in ('skin','joint') for row in c.calls))

    def test_pre_eye_cancel_does_not_record_input(self):
        host=self.eye_scene();c=host._cmds;c.history={};c.answers=['Cancel']
        self.assertIsNone(host.record_original_face_eye_input('Right'))
        self.assertNotIn('FaceFitSkeleton.RightEye',c.attrs)

    def test_fit_button_does_not_repeat_lattice_or_skin_for_saved_pre_input(self):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        from adv_py.application.face_pre import FaceSide
        host=self.eye_scene();c=host._cmds;c.attrs['FaceFitSkeleton.RightEye']='|EyeMesh'
        host._transaction_active=True
        def unexpected(*args):raise AssertionError('Choose Input repeated during Fit')
        host.ensure_original_face_input_skins=unexpected
        host.mark_original_non_spherical_eye_lattice=unexpected
        host.create_original_eye_ball_fit=lambda *args:'|FitEyeBall'
        self.assertEqual(MayaFacePreHost.create_eye_ball_fit(host,'|EyeMesh','Head_M',FaceSide.RIGHT),'|FitEyeBall')

    def test_lattice_dialog_repeats_and_retained_ffd_can_apply_to_next_mesh(self):
        host=Host();c=host._cmds;c.answers=['No','Yes']
        c.history={'eye1':['ffd','skin1'],'eye2':['skin2']}
        c.types={'ffd':'ffd','skin1':'skinCluster','skin2':'skinCluster'}
        self.assertEqual(host.mark_original_non_spherical_eye_lattice(('eye1','eye2'),'R'),('ffd',))
        self.assertEqual(len([row for row in c.calls if row[0]=='dialog']),2)
        self.assertIn(('reorder',('ffd','skin2','eye2')),c.calls)
        self.assertIn(('deleteAttr','ffd.asNonSphereLattice_L'),c.calls)
        self.assertFalse(any(row==('deleteAttr','ffd.userAttribute') for row in c.calls))

    def test_record_face_can_store_native_multiple_geometry_text(self):
        from adv_py.application.face_pre import RecordFacePreInput,FacePreRole
        class ApplicationHost:
            def transaction(self, label):return nullcontext()
            def selected_face_meshes(self):return ('|FaceA','|FaceB')
            def store_face_objects(self,role,meshes,head):self.stored=meshes
            def read_face_objects(self,role):return self.stored
        host=ApplicationHost()
        self.assertEqual(RecordFacePreInput(host).objects(FacePreRole.FACE,'Head_M'),('|FaceA','|FaceB'))

    def test_all_head_can_precede_face_input(self):
        from adv_py.application.face_pre import RecordFacePreInput,FacePreRole
        class ApplicationHost:
            def transaction(self, label):return nullcontext()
            def selected_face_meshes(self):return ('|Head',)
            def store_face_objects(self,role,meshes,head):self.stored=meshes
            def read_face_objects(self,role):return () if role is FacePreRole.FACE else self.stored
        self.assertEqual(RecordFacePreInput(ApplicationHost()).objects(FacePreRole.ALL_HEAD,'Head_M'),('|Head',))

    def test_all_head_requires_direct_selection_before_descendant_expansion(self):
        from adv_py.adapters.maya_face_pre import MayaFacePreHost
        class SelectionHost:
            _cmds=Commands()
            def read_face_objects(self,role):return ('|Group|Face',)
        host=SelectionHost();host._cmds.selection=['|Group']
        with self.assertRaises(FitSkeletonValidationError):
            MayaFacePreHost.validate_original_all_head_selection(host)
        host._cmds.selection=['|Group|Face']
        MayaFacePreHost.validate_original_all_head_selection(host)


if __name__=='__main__':unittest.main()
