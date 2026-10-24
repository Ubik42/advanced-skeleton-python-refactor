"""RP Fit pole visualization preserves native weighted baseline and vertices."""
import unittest

from adv_py.adapters.maya_source_fit_pole_vectors import MayaSourceFitPoleVectorsMixin
from adv_py.core.source_fit_pole_vectors import SourceFitPoleVector,source_fit_pole_vectors
from adv_py.core.fit_hierarchy import FitHierarchyNode,FitHierarchySnapshot
from adv_py.core.joint_labels import JointLabel


def arm_hierarchy():
    root='|FitSkeleton|Root'
    shoulder=root+'|Shoulder'
    elbow=shoulder+'|Elbow'
    hand=elbow+'|Wrist'
    hierarchy=FitHierarchySnapshot('|FitSkeleton',tuple(
        FitHierarchyNode(path,path.rsplit('|',1)[-1],parent,(x,y,z),(x,y,z))
        for path,parent,x,y,z in ((root,'|FitSkeleton',0.,10.,0.),
            (shoulder,root,-1.,15.,0.),(elbow,shoulder,-5.,12.,1.),(hand,elbow,-9.,10.,0.))))
    labels={joint.path:None for joint in hierarchy.joints}
    labels[shoulder]=JointLabel('Shoulder')
    labels[hand]=JointLabel('Hand')
    return hierarchy,labels


class GraphCommands:
    def __init__(self):
        self.connections=[]
        self.created=[]
        self.calls=[]

    def polyCreateFacet(self, **options):
        self.calls.append(('facet',options))
        return [options['name']]

    def polyNormal(self, *args, **options):
        self.calls.append(('normal',options))

    def parent(self, node, parent):
        return [node]

    def sets(self, *args, **options): pass
    def setAttr(self, *args, **options): pass
    def spaceLocator(self): return ['locator1']
    def rename(self, node, name): return name
    def duplicate(self, node, *,name): return [name]

    def createNode(self, kind, *,name):
        self.created.append((name,kind))
        return name

    def connectAttr(self, source, target, **options):
        self.connections.append((source,target))

    def pointConstraint(self, *args, **options):
        if options.get('query'):
            return ['startW0','endW1']
        return [args[-1]+'_pointConstraint1']

    def aimConstraint(self, *args, **options):
        self.calls.append(('aim',args,options))

    def listRelatives(self, node, **options):
        return [node+'Shape']


class SourceFitPoleVectorTests(unittest.TestCase):
    def test_only_rp_start_is_emitted_in_native_descendant_order(self):
        hierarchy,labels=arm_hierarchy()
        order=tuple(joint.path for joint in reversed(hierarchy.joints))
        plans=source_fit_pole_vectors(hierarchy,labels,order)
        self.assertEqual(plans,(SourceFitPoleVector('Arm',hierarchy.joints[1].path,
                             hierarchy.joints[2].path,hierarchy.joints[3].path),))

    def test_missing_hand_label_does_not_infer_an_ik_from_joint_names(self):
        hierarchy,labels=arm_hierarchy()
        labels[hierarchy.joints[-1].path]=None
        self.assertEqual(source_fit_pole_vectors(hierarchy,labels),())

    def test_graph_baseline_uses_opposite_segment_lengths_and_native_pma_sum(self):
        commands=GraphCommands()
        host=MayaSourceFitPoleVectorsMixin()
        host._cmds=commands
        host._create_fit_pole_vector(SourceFitPoleVector('Arm','Shoulder','Elbow','Wrist'))
        stem='VisualizePoleVector_Arm'
        self.assertIn((stem+'IKDistB.distance',stem+'IKMidFloat_pointConstraint1.startW0'),commands.connections)
        self.assertIn((stem+'IKDistA.distance',stem+'IKMidFloat_pointConstraint1.endW1'),commands.connections)
        self.assertIn((stem+'IKDist.distance',stem+'PMA.input1D[0]'),commands.connections)
        self.assertIn((stem+'IKDistC.distance',stem+'PMA.input1D[1]'),commands.connections)
        self.assertIn((stem+'PMA.output1D',stem+'IKPoleVec.tx'),commands.connections)
        aim=next(call for call in commands.calls if call[0]=='aim')
        self.assertEqual(aim[2]['worldUpObject'],'Shoulder')
        self.assertEqual(aim[2]['worldUpType'],'objectrotation')
        self.assertEqual(aim[2]['upVector'],(0.,0.,1.))

    def test_facet_corners_follow_parent_pole_child_middle_in_source_order(self):
        commands=GraphCommands()
        host=MayaSourceFitPoleVectorsMixin()
        host._cmds=commands
        host._create_fit_pole_vector(SourceFitPoleVector('Arm','Shoulder','Elbow','Wrist'))
        self.assertEqual(commands.connections[-4:],[
            ('VisualizePoleVector_Arm'+suffix+'.worldPosition[0]',
             'VisualizePoleVector_ArmShape.controlPoints['+str(index)+']')
            for index,suffix in enumerate(('IKParent','IKPoleVec','IKChild','IKMid'))])
        self.assertFalse(any(call[0]=='normal' for call in commands.calls))

    def test_only_exact_leg_name_reverses_normals(self):
        for name,expected in (('Leg',True),('Leg1',False)):
            commands=GraphCommands()
            host=MayaSourceFitPoleVectorsMixin()
            host._cmds=commands
            host._create_fit_pole_vector(SourceFitPoleVector(name,'Hip','Knee','Ankle'))
            self.assertEqual(any(call[0]=='normal' for call in commands.calls),expected)


if __name__=='__main__':unittest.main()
