"""Explicit influence redistribution across a changed spine joint count."""
from dataclasses import replace
import unittest

from adv_py.core import (SkinInfluenceWeight, SkinVertexWeights,
    SkinWeightInputState, SkinWeightValidationError,
    skin_weight_document_from_state, skin_weight_document_to_json,
    redistribute_skin_weight_document, linear_spine_weight_redistribution,
    registered_spine_weight_redistribution)
from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import CharacterBindJoint, CharacterRegistration
from adv_py.core.skin_weight_redistribution import (
    SkinWeightInfluenceRedistribution, SkinWeightRedistributionTarget)


SOURCE=("|Root", "|Spine1", "|Spine2", "|Chest")
TARGET=("|TargetRoot", "|TargetSpine1", "|TargetSpine2",
        "|TargetSpine3", "|TargetSpine4", "|TargetChest")


def document():
    return skin_weight_document_from_state(SkinWeightInputState(
        "SourceSkin", "|SourceMesh", 2, (*SOURCE, "|Arm"), (), 2, True,
        (SkinVertexWeights(0, (SkinInfluenceWeight("|Spine1", .5),
                               SkinInfluenceWeight("|Arm", .5))),
         SkinVertexWeights(1, (SkinInfluenceWeight("|Spine2", .75),
                               SkinInfluenceWeight("|Chest", .25))))))


def mapping():
    return linear_spine_weight_redistribution(SOURCE, TARGET,
        target_skin_name="TargetSkin", target_mesh_path="|TargetMesh",
                                    other_influences=(("|Arm", "|TargetArm"),))


def registration(namespace, spine_points):
    chain = ('Root_M', *(f'Spine{i}_M' for i in range(1, len(spine_points)-1)),
             'Chest_M')
    names = (*chain, 'Shoulder_R', 'Head_M')
    def matrix(y):
        return (1., 0., 0., 0., 0., 1., 0., 0.,
                0., 0., 1., 0., 0., float(y), 0., 1.)
    body = tuple(CharacterBindJoint('|' + name,
        None if index == 0 else '|' + names[index-1], matrix(
            spine_points[index] if index < len(chain) else spine_points[-1]))
        for index, name in enumerate(names))
    spine = BodySplinePlan('|Root_M', (), tuple('|' + name for name in chain),
        (), '', '', (), (), (), tuple(float(b-a)
            for a, b in zip(spine_points, spine_points[1:])))
    return CharacterRegistration('|Root_M', '|FitSkeleton', (), body, (), spine, None)


class SkinWeightRedistributionTests(unittest.TestCase):
    def test_registered_bind_positions_drive_partial_spine_influences(self):
        source = registration('source', (0, 2, 6, 10))
        target = registration('target', (0, 1, 3, 5, 8, 10))
        source_paths = ('|source:Spine1_M', '|source:Shoulder_R')
        target_paths = tuple('|target:' + path.rsplit('|', 1)[-1]
            for path in target.spine.body_joints) + ('|target:Shoulder_R',)
        result = registered_spine_weight_redistribution(source, target,
            source_paths, target_paths, target_skin_name='TargetSkin',
            target_mesh_path='|TargetMesh', source_namespace='source',
            target_namespace='target')
        spine = result.influences[0]
        self.assertEqual(spine.source_path, source_paths[0])
        self.assertEqual(tuple(row.path for row in spine.targets),
                         ('|target:Spine1_M', '|target:Spine2_M'))
        self.assertAlmostEqual(spine.targets[0].fraction, .5)
        self.assertAlmostEqual(spine.targets[1].fraction, .5)
        self.assertEqual(result.influences[1].targets[0].path,
                         '|target:Shoulder_R')
        with self.assertRaisesRegex(SkinWeightValidationError, '未映射'):
            registered_spine_weight_redistribution(source, target,
                source_paths, target_paths + ('|target:Head_M',),
                target_skin_name='TargetSkin', target_mesh_path='|TargetMesh',
                source_namespace='source', target_namespace='target')
        with self.assertRaisesRegex(SkinWeightValidationError, '完整'):
            registered_spine_weight_redistribution(source, target,
                source_paths, target_paths[1:], target_skin_name='TargetSkin',
                target_mesh_path='|TargetMesh', source_namespace='source',
                target_namespace='target')
        with self.assertRaisesRegex(SkinWeightValidationError, '命名空间'):
            registered_spine_weight_redistribution(source, target,
                ('|other:Spine1_M', source_paths[1]), target_paths,
                target_skin_name='TargetSkin', target_mesh_path='|TargetMesh',
                source_namespace='source', target_namespace='target')

    def test_spine_growth_splits_weight_without_loss(self):
        result=redistribute_skin_weight_document(document(),mapping())
        self.assertEqual(result.influence_paths,(*TARGET,"|TargetArm"))
        self.assertEqual(result.maximum_influences,3)
        weights={row.influence_path:row.weight for row in result.vertices[0].weights}
        self.assertEqual(set(weights),{"|TargetArm","|TargetSpine1","|TargetSpine2"})
        self.assertAlmostEqual(weights["|TargetArm"],.5)
        self.assertAlmostEqual(weights["|TargetSpine1"],1/6)
        self.assertAlmostEqual(weights["|TargetSpine2"],1/3)
        self.assertAlmostEqual(sum(row.weight for row in result.vertices[1].weights),1.)
        self.assertEqual(result.skin_name,"TargetSkin")
        self.assertEqual(result.mesh_path,"|TargetMesh")
        self.assertTrue(skin_weight_document_to_json(result))

    def test_rejects_missing_source_bad_fraction_and_unknown_target(self):
        source=document()
        plan=mapping()
        with self.assertRaisesRegex(SkinWeightValidationError,"完整"):
            redistribute_skin_weight_document(source,replace(plan,
                influences=plan.influences[:-1]))
        bad=replace(plan.influences[1],targets=(
            SkinWeightRedistributionTarget(TARGET[1],.2),
            SkinWeightRedistributionTarget(TARGET[2],.2)))
        with self.assertRaisesRegex(SkinWeightValidationError,"比例和"):
            redistribute_skin_weight_document(source,replace(plan,
                influences=(plan.influences[0],bad,*plan.influences[2:])))
        bad=SkinWeightInfluenceRedistribution("|Spine1",(
            SkinWeightRedistributionTarget("|Missing",1.),))
        with self.assertRaisesRegex(SkinWeightValidationError,"存在"):
            redistribute_skin_weight_document(source,replace(plan,
                influences=(plan.influences[0],bad,*plan.influences[2:])))

    def test_rejects_duplicate_paths(self):
        with self.assertRaisesRegex(SkinWeightValidationError,"重复"):
            linear_spine_weight_redistribution(SOURCE,TARGET,
                target_skin_name="TargetSkin",target_mesh_path="|TargetMesh",
                other_influences=(("|Spine1","|TargetArm"),))
        with self.assertRaisesRegex(SkinWeightValidationError,"重复"):
            linear_spine_weight_redistribution(SOURCE,TARGET,
                target_skin_name="TargetSkin",target_mesh_path="|TargetMesh",
                other_influences=(("|Arm",TARGET[1]),))

    def test_nonuniform_bind_positions_control_split(self):
        plan=linear_spine_weight_redistribution(SOURCE,TARGET,
            target_skin_name="TargetSkin",target_mesh_path="|TargetMesh",
            other_influences=(("|Arm","|TargetArm"),),
            source_positions=(0.,.2,.6,1.),
            target_positions=(0.,.1,.3,.5,.8,1.))
        result=redistribute_skin_weight_document(document(),plan)
        first={row.influence_path:row.weight for row in result.vertices[0].weights}
        self.assertAlmostEqual(first[TARGET[1]],.25)
        self.assertAlmostEqual(first[TARGET[2]],.25)
        with self.assertRaisesRegex(SkinWeightValidationError,"严格递增"):
            linear_spine_weight_redistribution(SOURCE,TARGET,
                target_skin_name="TargetSkin",target_mesh_path="|TargetMesh",
                source_positions=(0.,.2,.2,1.))


if __name__ == "__main__":
    unittest.main()
