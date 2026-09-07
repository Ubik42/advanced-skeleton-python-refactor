import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from adv_py.application import ExportSkinWeights, ImportSkinWeights
from adv_py.core import (
    SkinInfluenceWeight,
    SkinVertexWeights,
    SkinWeightInputState,
    SkinWeightValidationError,
    skin_weight_document_from_json,
    skin_weight_document_from_state,
    skin_weight_document_to_json,
)


A = "|JointA"
B = "|JointB"


def vertex(index, first, second):
    return SkinVertexWeights(
        index,
        (
            SkinInfluenceWeight(A, first),
            SkinInfluenceWeight(B, second),
        ),
    )


class FakeSkinWeightDocumentHost:
    def __init__(self):
        self.state = SkinWeightInputState(
            "AdvPy_BodySkin",
            "|BodyMesh",
            2,
            (A, B),
            (),
            2,
            True,
            (vertex(0, 0.7, 0.3), vertex(1, 0.3, 0.7)),
        )
        self.transaction_count = 0

    def capture_all_skin_weights(self, skin_name, mesh_path):
        del skin_name, mesh_path
        return self.state

    def capture_skin_weight_input(self, request):
        indices = {vertex.vertex_index for vertex in request.vertices}
        return replace(
            self.state,
            vertices=tuple(
                vertex
                for vertex in self.state.vertices
                if vertex.vertex_index in indices
            ),
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
        current = {vertex.vertex_index: vertex for vertex in self.state.vertices}
        for change in changes:
            current[change.vertex_index] = SkinVertexWeights(
                change.vertex_index,
                change.after,
            )
        self.state = replace(
            self.state,
            vertices=tuple(current[index] for index in sorted(current)),
        )


class SkinWeightIoTests(unittest.TestCase):
    def test_document_round_trip_has_stable_digest(self):
        state = FakeSkinWeightDocumentHost().state
        document = skin_weight_document_from_state(state)
        restored = skin_weight_document_from_json(
            skin_weight_document_to_json(document)
        )
        self.assertEqual(restored, document)
        self.assertEqual(len(document.content_sha256), 64)

    def test_tampered_document_is_rejected(self):
        document = skin_weight_document_from_state(
            FakeSkinWeightDocumentHost().state
        )
        data = json.loads(skin_weight_document_to_json(document))
        data["vertices"][0]["weights"][0]["weight"] = 0.6
        data["vertices"][0]["weights"][1]["weight"] = 0.4
        with self.assertRaisesRegex(SkinWeightValidationError, "摘要"):
            skin_weight_document_from_json(json.dumps(data))

    def test_export_is_atomic_and_refuses_existing_target(self):
        host = FakeSkinWeightDocumentHost()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "weights.json"
            result = ExportSkinWeights(host).apply(
                "AdvPy_BodySkin",
                "|BodyMesh",
                target,
            )
            self.assertGreater(result.bytes_written, 0)
            self.assertEqual(
                skin_weight_document_from_json(target.read_text("utf-8")),
                result.plan.document,
            )
            with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
                ExportSkinWeights(host).apply(
                    "AdvPy_BodySkin",
                    "|BodyMesh",
                    target,
                )

    def test_import_restores_document_and_repeat_is_noop(self):
        host = FakeSkinWeightDocumentHost()
        exported = host.state.vertices
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "weights.json"
            ExportSkinWeights(host).apply(
                "AdvPy_BodySkin",
                "|BodyMesh",
                target,
            )
            host.state = replace(
                host.state,
                vertices=(vertex(0, 0.2, 0.8), vertex(1, 0.8, 0.2)),
            )
            result = ImportSkinWeights(host).apply(target)
            self.assertEqual(result.edit_result.changed_vertex_count, 2)
            self.assertEqual(host.state.vertices, exported)
            self.assertEqual(host.transaction_count, 1)
            repeated = ImportSkinWeights(host).apply(target)
            self.assertEqual(repeated.edit_result.changed_vertex_count, 0)
            self.assertEqual(host.transaction_count, 1)

    def test_import_blocks_topology_mismatch_before_transaction(self):
        host = FakeSkinWeightDocumentHost()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "weights.json"
            ExportSkinWeights(host).apply(
                "AdvPy_BodySkin",
                "|BodyMesh",
                target,
            )
            host.state = replace(host.state, vertex_count=3)
            with self.assertRaisesRegex(ValueError, "顶点数"):
                ImportSkinWeights(host).apply(target)
            self.assertEqual(host.transaction_count, 0)


if __name__ == "__main__":
    unittest.main()
