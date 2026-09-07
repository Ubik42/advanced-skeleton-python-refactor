import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import MirrorSkinWeights
from adv_py.core import (
    SkinInfluenceWeight,
    SkinVertexWeights,
    SkinWeightInfluenceMapping,
    SkinWeightInputState,
    SkinWeightValidationError,
    SkinWeightVertexPair,
    plan_skin_weight_mirror,
    skin_weight_mirror_request,
)


R1 = "|RightA"
R2 = "|RightB"
L1 = "|LeftA"
L2 = "|LeftB"
C = "|Center"


def vertex(index, *weights):
    return SkinVertexWeights(
        index,
        tuple(SkinInfluenceWeight(path, value) for path, value in weights),
    )


def pairs():
    return (SkinWeightVertexPair(0, 4), SkinWeightVertexPair(1, 5))


def mappings():
    return (
        SkinWeightInfluenceMapping(R1, L1),
        SkinWeightInfluenceMapping(R2, L2),
        SkinWeightInfluenceMapping(C, C),
    )


class FakeSkinWeightMirrorHost:
    def __init__(self):
        self.state = SkinWeightInputState(
            "BodySkin",
            "|BodyMesh",
            6,
            (R1, R2, L1, L2, C),
            (),
            3,
            True,
            (
                vertex(0, (R1, 0.7), (C, 0.3)),
                vertex(1, (R2, 0.6), (C, 0.4)),
                vertex(2, (C, 1.0)),
                vertex(3, (C, 1.0)),
                vertex(4, (L1, 0.1), (L2, 0.9)),
                vertex(5, (L1, 0.9), (L2, 0.1)),
            ),
        )
        self.transaction_count = 0

    def _subset(self, indices):
        wanted = set(indices)
        return replace(
            self.state,
            vertices=tuple(
                item
                for item in self.state.vertices
                if item.vertex_index in wanted
            ),
        )

    def capture_skin_vertices(self, skin_name, mesh_path, vertex_indices):
        del skin_name, mesh_path
        return self._subset(vertex_indices)

    def capture_skin_weight_input(self, request):
        return self._subset(
            vertex.vertex_index for vertex in request.vertices
        )

    @contextmanager
    def transaction(self, label):
        del label
        before = self.state
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.state = before
            raise

    def apply_skin_weight_changes(self, request, changes):
        del request
        current = {item.vertex_index: item for item in self.state.vertices}
        for change in changes:
            current[change.vertex_index] = SkinVertexWeights(
                change.vertex_index,
                change.after,
            )
        self.state = replace(
            self.state,
            vertices=tuple(current[index] for index in sorted(current)),
        )


class SkinWeightMirrorTests(unittest.TestCase):
    def test_rejects_overlapping_vertices_and_non_bijective_influences(self):
        with self.assertRaisesRegex(SkinWeightValidationError, "互不重叠"):
            skin_weight_mirror_request(
                "BodySkin",
                "|BodyMesh",
                (SkinWeightVertexPair(0, 1), SkinWeightVertexPair(1, 2)),
                mappings(),
            )
        with self.assertRaisesRegex(SkinWeightValidationError, "一一对应"):
            skin_weight_mirror_request(
                "BodySkin",
                "|BodyMesh",
                pairs(),
                (
                    SkinWeightInfluenceMapping(R1, L1),
                    SkinWeightInfluenceMapping(R2, L1),
                ),
            )

    def test_plans_mapped_weights_with_identity_center_influence(self):
        host = FakeSkinWeightMirrorHost()
        request = skin_weight_mirror_request(
            "BodySkin",
            "|BodyMesh",
            pairs(),
            mappings(),
        )
        targets = plan_skin_weight_mirror(
            request,
            host._subset((0, 1)),
            host._subset((4, 5)),
        )
        self.assertEqual(
            targets,
            (
                vertex(4, (C, 0.3), (L1, 0.7)),
                vertex(5, (C, 0.4), (L2, 0.6)),
            ),
        )

    def test_preflight_reports_unmapped_source_weight(self):
        host = FakeSkinWeightMirrorHost()
        plan = MirrorSkinWeights(host).plan(
            "BodySkin",
            "|BodyMesh",
            pairs(),
            (
                SkinWeightInfluenceMapping(R1, L1),
                SkinWeightInfluenceMapping(R2, L2),
            ),
        )
        self.assertFalse(plan.ready)
        self.assertIn(
            "unmapped_source_influence",
            {issue.code for issue in plan.input_issues},
        )
        self.assertEqual(host.transaction_count, 0)

    def test_mirrors_once_preserves_source_and_repeat_is_noop(self):
        host = FakeSkinWeightMirrorHost()
        source_before = host._subset((0, 1)).vertices
        result = MirrorSkinWeights(host).apply(
            "BodySkin",
            "|BodyMesh",
            pairs(),
            mappings(),
        )
        self.assertEqual(result.edit_result.changed_vertex_count, 2)
        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(host._subset((0, 1)).vertices, source_before)
        repeated = MirrorSkinWeights(host).apply(
            "BodySkin",
            "|BodyMesh",
            pairs(),
            mappings(),
        )
        self.assertEqual(repeated.edit_result.changed_vertex_count, 0)
        self.assertEqual(host.transaction_count, 1)


if __name__ == "__main__":
    unittest.main()
