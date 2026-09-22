"""Cross-topology interpolation and refusal boundaries."""
from dataclasses import replace
import json
import unittest

from adv_py.core import (FaceMeshSnapshot, FaceSurfaceAlignment, SkinInfluenceWeight,
    SkinVertexWeights, SkinWeightInputState, SkinWeightValidationError,
    skin_weight_document_from_state, transfer_skin_weights_by_surface)
from adv_py.core.face_neutral_geometry import FaceNeutralGeometry
from adv_py.core.skin_weight_surface_source import (SkinWeightSurfaceSource,
    skin_weight_surface_source_from_json, skin_weight_surface_source_to_json)


class SkinWeightSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.source_mesh = FaceMeshSnapshot("|Source", 3, "a" * 64,
            ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.)))
        self.target_mesh = FaceMeshSnapshot("|Target", 4, "b" * 64,
            self.source_mesh.points + ((.25, .25, 0.),))
        self.source = skin_weight_document_from_state(SkinWeightInputState(
            "SourceSkin", "|Source", 3, ("|A", "|B"), (), 2, True,
            (SkinVertexWeights(0, (SkinInfluenceWeight("|A", 1.),)),
             SkinVertexWeights(1, (SkinInfluenceWeight("|B", 1.),)),
             SkinVertexWeights(2, (SkinInfluenceWeight("|A", 1.),)))))
        self.target = SkinWeightInputState("TargetSkin", "|Target", 4,
            ("|A", "|B"), (), 2, True, ())

    def test_interpolates_complete_document(self):
        result = transfer_skin_weights_by_surface(self.source, self.source_mesh,
            self.target_mesh, ((0, 1, 2),), self.target, max_distance=0.)
        self.assertEqual(result.document.vertex_count, 4)
        self.assertEqual(result.document.vertices[3].weights,
            (SkinInfluenceWeight("|A", .75), SkinInfluenceWeight("|B", .25)))
        self.assertEqual(result.max_surface_distance, 0.)

    def test_rejects_distance_influence_and_loss(self):
        raised = replace(self.target_mesh, points=self.target_mesh.points[:3]
                         + ((.25, .25, 2.),))
        with self.assertRaisesRegex(ValueError, "超过最大允许距离"):
            transfer_skin_weights_by_surface(self.source, self.source_mesh,
                raised, ((0, 1, 2),), self.target, max_distance=.1)
        with self.assertRaisesRegex(SkinWeightValidationError, "influence 集合不同"):
            transfer_skin_weights_by_surface(self.source, self.source_mesh,
                self.target_mesh, ((0, 1, 2),), replace(self.target,
                influence_paths=("|A", "|C")), max_distance=0.)
        limited = replace(self.target, maximum_influences=1)
        with self.assertRaisesRegex(SkinWeightValidationError, "裁剪损失"):
            transfer_skin_weights_by_surface(self.source, self.source_mesh,
                self.target_mesh, ((0, 1, 2),), limited, max_distance=0.)
        result = transfer_skin_weights_by_surface(self.source, self.source_mesh,
            self.target_mesh, ((0, 1, 2),), limited, max_distance=0.,
            max_discarded_weight=.26)
        self.assertAlmostEqual(result.max_discarded_weight, .25)
        self.assertEqual(result.document.vertices[3].weights,
                         (SkinInfluenceWeight("|A", 1.),))

    def test_portable_source_binds_geometry_and_weights(self):
        source = SkinWeightSurfaceSource(self.source,
            FaceNeutralGeometry(self.source_mesh, ((0, 1, 2),), "y", "cm"))
        text = skin_weight_surface_source_to_json(source)
        self.assertEqual(skin_weight_surface_source_from_json(text), source)
        damaged = json.loads(text)
        damaged["payload"]["geometry"]["payload"]["points"][0][0] = 99.
        with self.assertRaisesRegex(ValueError, "摘要"):
            skin_weight_surface_source_from_json(json.dumps(damaged))
        with self.assertRaisesRegex(ValueError, "重复字段"):
            skin_weight_surface_source_from_json(text.replace(
                '"version": 1\n}', '"version": 1, "version": 1\n}', 1))
        with self.assertRaisesRegex(ValueError, "同一网格"):
            SkinWeightSurfaceSource(self.source, FaceNeutralGeometry(
                replace(self.source_mesh, path="|Other"), ((0, 1, 2),), "y", "cm"))

    def test_rigid_alignment_transfers_translated_rotated_mesh(self):
        moved = replace(self.target_mesh, points=tuple(
            (5. - point[1], 2. + point[0], point[2])
            for point in self.target_mesh.points))
        with self.assertRaisesRegex(ValueError, "超过最大允许距离"):
            transfer_skin_weights_by_surface(self.source, self.source_mesh,
                moved, ((0, 1, 2),), self.target, max_distance=0.)
        result = transfer_skin_weights_by_surface(self.source, self.source_mesh,
            moved, ((0, 1, 2),), self.target, max_distance=0.,
            alignment=FaceSurfaceAlignment(((0, 0), (1, 1), (2, 2)), 1e-6))
        self.assertEqual(result.document.vertices[3].weights,
            (SkinInfluenceWeight("|A", .75), SkinInfluenceWeight("|B", .25)))

    def test_explicit_policy_allows_extra_target_influence_with_zero_weights(self):
        extra = replace(self.target, influence_paths=("|A", "|B", "|Extra"))
        with self.assertRaisesRegex(SkinWeightValidationError, "influence 集合不同"):
            transfer_skin_weights_by_surface(self.source, self.source_mesh,
                self.target_mesh, ((0, 1, 2),), extra, max_distance=0.)
        result = transfer_skin_weights_by_surface(self.source, self.source_mesh,
            self.target_mesh, ((0, 1, 2),), extra, max_distance=0.,
            allow_target_extra_influences=True)
        self.assertEqual(result.document.influence_paths, ("|A", "|B", "|Extra"))
        self.assertTrue(all("|Extra" not in (entry.influence_path
            for entry in vertex.weights) for vertex in result.document.vertices))


if __name__ == "__main__":
    unittest.main()
