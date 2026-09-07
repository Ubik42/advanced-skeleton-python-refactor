import unittest
from contextlib import contextmanager
from dataclasses import replace

from adv_py.application import MirrorSkinWeightsByGeometry
from adv_py.core import (
    SkinInfluenceWeight,
    SkinMeshGeometryState,
    SkinMeshVertexPosition,
    SkinVertexWeights,
    SkinWeightInfluenceMapping,
    SkinWeightInputState,
    SkinWeightMirrorDirection,
    SkinWeightValidationError,
    SkinWeightVertexPair,
    plan_skin_weight_geometry_pairs,
    skin_weight_geometry_mirror_request,
)


RIGHT = "|Right"
LEFT = "|Left"
CENTER = "|Center"


def vertex(index, *weights):
    return SkinVertexWeights(
        index,
        tuple(SkinInfluenceWeight(path, value) for path, value in weights),
    )


def mappings():
    return (
        SkinWeightInfluenceMapping(RIGHT, LEFT),
        SkinWeightInfluenceMapping(CENTER, CENTER),
    )


def symmetric_geometry():
    return SkinMeshGeometryState(
        "|BodyMesh",
        5,
        (
            SkinMeshVertexPosition(0, (-2.0, 0.0, 0.0)),
            SkinMeshVertexPosition(1, (-1.0, 1.0, 0.0)),
            SkinMeshVertexPosition(2, (0.0, 2.0, 0.0)),
            SkinMeshVertexPosition(3, (1.0, 1.0, 0.0)),
            SkinMeshVertexPosition(4, (2.0, 0.0, 0.0)),
        ),
    )


class FakeGeometryMirrorHost:
    def __init__(self):
        self.geometry = symmetric_geometry()
        self.state = SkinWeightInputState(
            "BodySkin",
            "|BodyMesh",
            5,
            (RIGHT, LEFT, CENTER),
            (),
            2,
            True,
            (
                vertex(0, (RIGHT, 0.8), (CENTER, 0.2)),
                vertex(1, (RIGHT, 0.6), (CENTER, 0.4)),
                vertex(2, (CENTER, 1.0)),
                vertex(3, (LEFT, 1.0)),
                vertex(4, (LEFT, 1.0)),
            ),
        )
        self.transaction_count = 0

    def capture_mesh_vertex_positions(self, mesh_path):
        del mesh_path
        return self.geometry

    def _subset(self, indices):
        wanted = set(indices)
        return replace(
            self.state,
            vertices=tuple(
                item for item in self.state.vertices if item.vertex_index in wanted
            ),
        )

    def capture_skin_vertices(self, skin_name, mesh_path, vertex_indices):
        del skin_name, mesh_path
        return self._subset(vertex_indices)

    def capture_skin_weight_input(self, request):
        return self._subset(item.vertex_index for item in request.vertices)

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


class SkinWeightGeometryTests(unittest.TestCase):
    def test_builds_deterministic_pairs_and_ignores_center_vertices(self):
        request = skin_weight_geometry_mirror_request(
            "BodySkin",
            "|BodyMesh",
            SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE,
            mappings(),
        )
        pairs, issues = plan_skin_weight_geometry_pairs(
            request,
            symmetric_geometry(),
        )
        self.assertEqual(issues, ())
        self.assertEqual(
            pairs,
            (SkinWeightVertexPair(0, 4), SkinWeightVertexPair(1, 3)),
        )

    def test_rejects_invalid_tolerance_and_asymmetric_geometry(self):
        with self.assertRaisesRegex(SkinWeightValidationError, "正有限数"):
            skin_weight_geometry_mirror_request(
                "BodySkin",
                "|BodyMesh",
                SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE,
                mappings(),
                tolerance=0.0,
            )
        request = skin_weight_geometry_mirror_request(
            "BodySkin",
            "|BodyMesh",
            SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE,
            mappings(),
        )
        state = replace(
            symmetric_geometry(),
            vertices=symmetric_geometry().vertices[:-1]
            + (SkinMeshVertexPosition(4, (2.25, 0.0, 0.0)),),
        )
        pairs, issues = plan_skin_weight_geometry_pairs(request, state)
        self.assertEqual(pairs, ())
        self.assertIn("mirrored_vertex_missing", {issue.code for issue in issues})

    def test_applies_generated_pairs_once_and_repeat_is_noop(self):
        host = FakeGeometryMirrorHost()
        source_before = host._subset((0, 1)).vertices
        operation = MirrorSkinWeightsByGeometry(host)
        result = operation.apply(
            "BodySkin",
            "|BodyMesh",
            SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE,
            mappings(),
        )
        self.assertEqual(result.mirror_result.edit_result.changed_vertex_count, 2)
        self.assertEqual(host.transaction_count, 1)
        self.assertEqual(host._subset((0, 1)).vertices, source_before)
        self.assertEqual(
            host._subset((3, 4)).vertices,
            (
                vertex(3, (CENTER, 0.4), (LEFT, 0.6)),
                vertex(4, (CENTER, 0.2), (LEFT, 0.8)),
            ),
        )
        repeated = operation.apply(
            "BodySkin",
            "|BodyMesh",
            SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE,
            mappings(),
        )
        self.assertEqual(repeated.mirror_result.edit_result.changed_vertex_count, 0)
        self.assertEqual(host.transaction_count, 1)

    def test_preflight_does_not_modify_when_target_influence_is_locked(self):
        host = FakeGeometryMirrorHost()
        host.state = replace(host.state, locked_influences=(LEFT,))
        plan = MirrorSkinWeightsByGeometry(host).plan(
            "BodySkin",
            "|BodyMesh",
            SkinWeightMirrorDirection.NEGATIVE_TO_POSITIVE,
            mappings(),
        )
        self.assertFalse(plan.ready)
        self.assertIn(
            "target_influence_locked",
            {issue.code for issue in plan.mirror_plan.input_issues},
        )
        self.assertEqual(host.transaction_count, 0)


if __name__ == "__main__":
    unittest.main()
