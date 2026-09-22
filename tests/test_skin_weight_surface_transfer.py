"""Cross-topology interpolation and refusal boundaries."""
from dataclasses import replace
import unittest

from adv_py.core import (FaceMeshSnapshot, SkinInfluenceWeight,
    SkinVertexWeights, SkinWeightInputState, SkinWeightValidationError,
    skin_weight_document_from_state, transfer_skin_weights_by_surface)


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


if __name__ == "__main__":
    unittest.main()
